import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

import '../../app/config.dart';
import 'audio_pipeline.dart';

enum SpeechEvent { started, ended }

class VoiceActivityDetector {
  VoiceActivityDetector({
    this.threshold = AppConfig.speechThreshold,
    this.endSilence = AppConfig.speechEndSilence,
  });

  final double threshold;
  final Duration endSilence;
  bool _speaking = false;
  DateTime? _lastVoiceAt;

  bool get isSpeaking => _speaking;

  SpeechEvent? update(double level, DateTime now) {
    if (level >= threshold) {
      _lastVoiceAt = now;
      if (!_speaking) {
        _speaking = true;
        return SpeechEvent.started;
      }
    } else if (_speaking &&
        _lastVoiceAt != null &&
        now.difference(_lastVoiceAt!) >= endSilence) {
      _speaking = false;
      return SpeechEvent.ended;
    }
    return null;
  }
}

class MicrophoneService {
  MicrophoneService({
    AudioRecorder? recorder,
    this.config = const AudioPipelineConfig(),
  })  : _recorder = recorder ?? AudioRecorder(),
        _adaptiveVad = AdaptiveVoiceActivityDetector(config),
        _turnDetector = TurnDetector(config);

  final AudioRecorder _recorder;
  final AudioPipelineConfig config;
  final AdaptiveVoiceActivityDetector _adaptiveVad;
  final TurnDetector _turnDetector;
  final StreamController<double> _levels = StreamController.broadcast();
  final StreamController<Uint8List> _chunks = StreamController.broadcast();
  final StreamController<SpeechEvent> _speechEvents =
      StreamController.broadcast();
  final StreamController<AudioFrameMetrics> _metrics =
      StreamController.broadcast();
  StreamSubscription<Uint8List>? _audioSubscription;
  bool _running = false;

  Stream<double> get levelStream => _levels.stream;
  Stream<Uint8List> get audioStream => _chunks.stream;
  Stream<SpeechEvent> get speechEvents => _speechEvents.stream;
  Stream<AudioFrameMetrics> get metrics => _metrics.stream;
  bool get isRunning => _running;
  bool get speechDetected =>
      _turnDetector.state == TurnState.listening ||
      _turnDetector.state == TurnState.maybeEnd;

  void resetForListening() {
    _turnDetector.reset();
    _adaptiveVad.recalibrate();
  }

  Future<void> start() async {
    if (_running) return;
    if (!await _recorder.hasPermission()) {
      throw StateError('Microphone permission not granted');
    }
    final stream = await _recorder.startStream(
      RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: config.sampleRate,
        numChannels: 1,
        autoGain: true,
        echoCancel: true,
        noiseSuppress: true,
      ),
    );
    _running = true;
    _audioSubscription = stream.listen(_handleChunk);
  }

  void _handleChunk(Uint8List chunk) {
    if (chunk.isEmpty) return;
    _chunks.add(chunk);
    final level = pcm16Rms(chunk);
    _levels.add(level);
    final frameMetrics = _adaptiveVad.analyze(chunk, _turnDetector.state);
    _metrics.add(frameMetrics);
    final transition = _turnDetector.update(
      frameMetrics.vadState,
      Duration(milliseconds: config.chunkMs),
    );
    if (transition?.speechStarted == true) {
      _speechEvents.add(SpeechEvent.started);
    }
    if (transition?.speechEnded == true) {
      _speechEvents.add(SpeechEvent.ended);
    }
  }

  static double pcm16Rms(Uint8List bytes) {
    return AdaptiveVoiceActivityDetector.pcm16Rms(bytes);
  }

  Future<void> stop() async {
    if (!_running) return;
    _running = false;
    await _audioSubscription?.cancel();
    await _recorder.stop();
  }

  Future<void> dispose() async {
    await stop();
    await _recorder.dispose();
    await _levels.close();
    await _chunks.close();
    await _speechEvents.close();
    await _metrics.close();
  }
}
