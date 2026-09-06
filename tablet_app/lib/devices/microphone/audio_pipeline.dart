import 'dart:collection';
import 'dart:math' as math;
import 'dart:typed_data';

enum VadState { silence, maybeSpeech, speech }

enum TurnState { idle, preSpeech, listening, maybeEnd, endOfTurn }

class AudioPipelineConfig {
  const AudioPipelineConfig({
    this.sampleRate = 16000,
    this.channels = 1,
    this.bitDepth = 16,
    this.chunkMs = 50,
    this.noiseMarginDb = 8,
    this.minimumThresholdDb = -58,
    this.maximumThresholdDb = -28,
    this.speechStartConfirmation = const Duration(milliseconds: 100),
    this.endTurnSilence = const Duration(milliseconds: 800),
    this.preRoll = const Duration(milliseconds: 500),
    this.postRoll = const Duration(milliseconds: 200),
    this.bargeInConfirmation = const Duration(milliseconds: 200),
    this.maxQueuedChunks = 80,
  });

  final int sampleRate;
  final int channels;
  final int bitDepth;
  final int chunkMs;
  final double noiseMarginDb;
  final double minimumThresholdDb;
  final double maximumThresholdDb;
  final Duration speechStartConfirmation;
  final Duration endTurnSilence;
  final Duration preRoll;
  final Duration postRoll;
  final Duration bargeInConfirmation;
  final int maxQueuedChunks;

  int get bytesPerChunk =>
      sampleRate * channels * (bitDepth ~/ 8) * chunkMs ~/ 1000;
}

class AudioFrameMetrics {
  const AudioFrameMetrics({
    required this.rms,
    required this.dbfs,
    required this.noiseFloorDb,
    required this.dynamicThresholdDb,
    required this.vadState,
    required this.speechProbability,
    required this.turnState,
  });

  final double rms;
  final double dbfs;
  final double noiseFloorDb;
  final double dynamicThresholdDb;
  final VadState vadState;
  final double speechProbability;
  final TurnState turnState;
}

class NoiseFloorEstimator {
  NoiseFloorEstimator({double initialDb = -60}) : _value = initialDb;

  double _value;
  double get value => _value;

  void calibrate(double dbfs) {
    if (!dbfs.isFinite) return;
    final bounded = dbfs.clamp(-90.0, -20.0);
    _value += (bounded - _value) * 0.25;
  }

  void update(double dbfs, {required bool speech}) {
    if (speech || !dbfs.isFinite) return;
    final bounded = dbfs.clamp(-90.0, -20.0);
    final rate = bounded < _value ? 0.08 : 0.012;
    _value += (bounded - _value) * rate;
  }
}

class AdaptiveVoiceActivityDetector {
  AdaptiveVoiceActivityDetector(this.config, {NoiseFloorEstimator? noiseFloor})
      : noiseFloor = noiseFloor ?? NoiseFloorEstimator();

  final AudioPipelineConfig config;
  final NoiseFloorEstimator noiseFloor;
  int _calibrationFrames = 20;

  void recalibrate() {
    _calibrationFrames = 10;
  }

  AudioFrameMetrics analyze(Uint8List pcm, TurnState turnState) {
    final rms = pcm16Rms(pcm);
    final dbfs = rms <= 0 ? -96.0 : 20 * math.log(rms) / math.ln10;
    if (_calibrationFrames > 0) {
      noiseFloor.calibrate(dbfs);
      _calibrationFrames--;
      return AudioFrameMetrics(
        rms: rms,
        dbfs: dbfs,
        noiseFloorDb: noiseFloor.value,
        dynamicThresholdDb: noiseFloor.value + config.noiseMarginDb,
        vadState: VadState.silence,
        speechProbability: 0,
        turnState: turnState,
      );
    }
    final threshold = (noiseFloor.value + config.noiseMarginDb)
        .clamp(config.minimumThresholdDb, config.maximumThresholdDb)
        .toDouble();
    final delta = dbfs - threshold;
    final probability = (1 / (1 + math.exp(-delta / 2.8))).clamp(0.0, 1.0);
    final state = probability >= 0.68
        ? VadState.speech
        : probability >= 0.38
            ? VadState.maybeSpeech
            : VadState.silence;
    noiseFloor.update(dbfs, speech: state == VadState.speech);
    return AudioFrameMetrics(
      rms: rms,
      dbfs: dbfs,
      noiseFloorDb: noiseFloor.value,
      dynamicThresholdDb: threshold,
      vadState: state,
      speechProbability: probability,
      turnState: turnState,
    );
  }

  static double pcm16Rms(Uint8List bytes) {
    final count = bytes.length ~/ 2;
    if (count == 0) return 0;
    final samples = ByteData.sublistView(bytes);
    var squares = 0.0;
    for (var i = 0; i < count; i++) {
      final value = samples.getInt16(i * 2, Endian.little) / 32768.0;
      squares += value * value;
    }
    return math.sqrt(squares / count).clamp(0.0, 1.0);
  }
}

class TurnTransition {
  const TurnTransition(this.from, this.to,
      {this.speechStarted = false, this.speechEnded = false});
  final TurnState from;
  final TurnState to;
  final bool speechStarted;
  final bool speechEnded;
}

class TurnDetector {
  TurnDetector(this.config);
  final AudioPipelineConfig config;
  TurnState state = TurnState.idle;
  Duration _speechRun = Duration.zero;
  Duration _silenceRun = Duration.zero;

  TurnTransition? update(VadState vad, Duration frameDuration) {
    final previous = state;
    if (vad == VadState.speech) {
      _speechRun += frameDuration;
      _silenceRun = Duration.zero;
      if (state == TurnState.idle) state = TurnState.preSpeech;
      if ((state == TurnState.preSpeech &&
              _speechRun >= config.speechStartConfirmation) ||
          state == TurnState.maybeEnd) {
        state = TurnState.listening;
      }
    } else {
      _speechRun = Duration.zero;
      if (state == TurnState.preSpeech) state = TurnState.idle;
      if (state == TurnState.listening || state == TurnState.maybeEnd) {
        _silenceRun += frameDuration;
        state = TurnState.maybeEnd;
        if (_silenceRun >= config.endTurnSilence + config.postRoll) {
          state = TurnState.endOfTurn;
        }
      }
    }
    if (state == previous) return null;
    final transition = TurnTransition(
      previous,
      state,
      speechStarted:
          previous == TurnState.preSpeech && state == TurnState.listening,
      speechEnded: state == TurnState.endOfTurn,
    );
    if (state == TurnState.endOfTurn) reset();
    return transition;
  }

  void reset() {
    state = TurnState.idle;
    _speechRun = Duration.zero;
    _silenceRun = Duration.zero;
  }
}

class PreRollBuffer {
  PreRollBuffer(AudioPipelineConfig config)
      : _capacity =
            math.max(1, config.preRoll.inMilliseconds ~/ config.chunkMs);
  final int _capacity;
  final Queue<Uint8List> _frames = Queue<Uint8List>();

  void add(Uint8List frame) {
    _frames.add(Uint8List.fromList(frame));
    while (_frames.length > _capacity) {
      _frames.removeFirst();
    }
  }

  List<Uint8List> drain() {
    final result = _frames.toList(growable: false);
    _frames.clear();
    return result;
  }
}
