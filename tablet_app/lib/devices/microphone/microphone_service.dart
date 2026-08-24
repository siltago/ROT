import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:record/record.dart';

import '../../app/config.dart';

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
  MicrophoneService({AudioRecorder? recorder, VoiceActivityDetector? detector})
      : _recorder = recorder ?? AudioRecorder(),
        _detector = detector ?? VoiceActivityDetector();

  final AudioRecorder _recorder;
  final VoiceActivityDetector _detector;
  final StreamController<double> _levels = StreamController.broadcast();
  final StreamController<Uint8List> _chunks = StreamController.broadcast();
  final StreamController<SpeechEvent> _speechEvents = StreamController.broadcast();
  StreamSubscription<Uint8List>? _audioSubscription;
  bool _running = false;

  Stream<double> get levelStream => _levels.stream;
  Stream<Uint8List> get audioStream => _chunks.stream;
  Stream<SpeechEvent> get speechEvents => _speechEvents.stream;
  bool get isRunning => _running;
  bool get speechDetected => _detector.isSpeaking;

  Future<void> start() async {
    if (_running) return;
    if (!await _recorder.hasPermission()) {
      throw StateError('Microphone permission not granted');
    }
    final stream = await _recorder.startStream(
      const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: AppConfig.audioSampleRate,
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
    final event = _detector.update(level, DateTime.now());
    if (event != null) _speechEvents.add(event);
  }

  static double pcm16Rms(Uint8List bytes) {
    final sampleCount = bytes.length ~/ 2;
    if (sampleCount == 0) return 0;
    final data = ByteData.sublistView(bytes);
    var sumSquares = 0.0;
    for (var index = 0; index < sampleCount; index++) {
      final sample = data.getInt16(index * 2, Endian.little) / 32768.0;
      sumSquares += sample * sample;
    }
    return math.sqrt(sumSquares / sampleCount).clamp(0.0, 1.0).toDouble();
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
  }
}
