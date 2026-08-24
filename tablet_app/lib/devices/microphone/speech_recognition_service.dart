import 'dart:async';

import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

class RecognizedSpeech {
  const RecognizedSpeech({
    required this.text,
    required this.isFinal,
    required this.confidence,
  });

  final String text;
  final bool isFinal;
  final double? confidence;
}

class SpeechRecognitionService {
  SpeechRecognitionService({SpeechToText? speech}) : _speech = speech ?? SpeechToText();

  final SpeechToText _speech;
  final StreamController<RecognizedSpeech> _results = StreamController.broadcast();
  final StreamController<double> _levels = StreamController.broadcast();
  final StreamController<bool> _listening = StreamController.broadcast();
  Timer? _restartTimer;
  bool _starting = false;
  bool _enabled = false;
  bool _available = false;
  String _lastFinalText = '';

  Stream<RecognizedSpeech> get results => _results.stream;
  Stream<double> get levels => _levels.stream;
  Stream<bool> get listening => _listening.stream;
  bool get isAvailable => _available;

  Future<bool> initialize() async {
    _available = await _speech.initialize(
      onStatus: _handleStatus,
      onError: _handleError,
      debugLogging: false,
    );
    return _available;
  }

  Future<void> start() async {
    _enabled = true;
    if (!_available || _speech.isListening || _starting) return;
    _starting = true;
    _lastFinalText = '';
    try {
      await _speech.listen(
        onResult: _handleResult,
        onSoundLevelChange: (level) {
          final normalized = ((level + 2) / 12).clamp(0.0, 1.0).toDouble();
          if (!_levels.isClosed) _levels.add(normalized);
        },
        listenOptions: SpeechListenOptions(
          partialResults: true,
          cancelOnError: false,
          listenMode: ListenMode.dictation,
          autoPunctuation: true,
          localeId: 'pt_BR',
          listenFor: const Duration(minutes: 1),
          pauseFor: const Duration(seconds: 3),
        ),
      );
    } finally {
      _starting = false;
    }
  }

  void _handleResult(SpeechRecognitionResult result) {
    final text = result.recognizedWords.trim();
    if (text.isEmpty) return;
    if (result.finalResult && text == _lastFinalText) return;
    if (result.finalResult) _lastFinalText = text;
    final confidence = result.hasConfidenceRating ? result.confidence : null;
    _results.add(
      RecognizedSpeech(text: text, isFinal: result.finalResult, confidence: confidence),
    );
  }

  void _handleStatus(String status) {
    final active = status == SpeechToText.listeningStatus;
    if (!_listening.isClosed) _listening.add(active);
    if (!active && _enabled) _scheduleRestart();
  }

  void _handleError(SpeechRecognitionError error) {
    if (!_listening.isClosed) _listening.add(false);
    if (_enabled && !error.permanent) _scheduleRestart();
  }

  void _scheduleRestart() {
    _restartTimer?.cancel();
    _restartTimer = Timer(const Duration(milliseconds: 800), () {
      if (_enabled) unawaited(_restart());
    });
  }

  Future<void> _restart() async {
    if (!_enabled || _starting) return;
    if (_speech.isListening) await _speech.stop();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    if (_enabled) await start();
  }

  Future<void> stop() async {
    _enabled = false;
    _restartTimer?.cancel();
    await _speech.stop();
  }

  Future<void> dispose() async {
    await stop();
    await _results.close();
    await _levels.close();
    await _listening.close();
  }
}
