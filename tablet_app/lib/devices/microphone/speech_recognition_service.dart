import 'dart:async';

import 'package:logger/logger.dart';
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
  SpeechRecognitionService({SpeechToText? speech})
      : _speech = speech ?? SpeechToText();

  final SpeechToText _speech;
  final Logger _logger = Logger();
  final StreamController<RecognizedSpeech> _results =
      StreamController.broadcast();
  final StreamController<double> _levels = StreamController.broadcast();
  final StreamController<bool> _listening = StreamController.broadcast();
  Timer? _restartTimer;
  bool _starting = false;
  bool _enabled = false;
  bool _available = false;
  String _lastFinalText = '';
  int _consecutiveRestartFailures = 0;
  bool _needsReinitialize = false;

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
    if (!_available) {
      _logger.w('SpeechToText.initialize() returned unavailable');
    }
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
          // `dictation` routed this device to an "AMBIENT_CONTINUOUS" ASR
          // domain with a very aggressive endpointer -- it would report
          // #onStartOfSpeech and then stop itself within ~60ms, before any
          // words came through. `confirmation` (built for short phrases,
          // which a wake word is) doesn't show that behavior.
          listenMode: ListenMode.confirmation,
          autoPunctuation: true,
          localeId: 'pt_BR',
          listenFor: const Duration(minutes: 1),
          pauseFor: const Duration(seconds: 3),
        ),
      );
      _consecutiveRestartFailures = 0;
    } catch (error, stackTrace) {
      _logger.e('SpeechToText.listen() failed',
          error: error, stackTrace: stackTrace);
    } finally {
      _starting = false;
    }
  }

  void _handleResult(SpeechRecognitionResult result) {
    final text = result.recognizedWords.trim();
    _logger.i(
      'SpeechToText result: "$text" (final: ${result.finalResult}, confidence: ${result.confidence})',
    );
    if (text.isEmpty) return;
    if (result.finalResult && text == _lastFinalText) return;
    if (result.finalResult) _lastFinalText = text;
    final confidence = result.hasConfidenceRating ? result.confidence : null;
    _results.add(
      RecognizedSpeech(
          text: text, isFinal: result.finalResult, confidence: confidence),
    );
  }

  void _handleStatus(String status) {
    final active = status == SpeechToText.listeningStatus;
    if (!_listening.isClosed) _listening.add(active);
    if (!active && _enabled) _scheduleRestart();
  }

  void _handleError(SpeechRecognitionError error) {
    if (!_listening.isClosed) _listening.add(false);
    _logger.w(
        'SpeechToText error: ${error.errorMsg} (permanent: ${error.permanent})');
    // The plugin's docs call `permanent` errors ones that "block speech
    // recognition from continuing" -- in practice that includes plain
    // error_speech_timeout on this device, which fires almost immediately
    // in a quiet room. Just calling start() again after that does nothing
    // (the recognizer considers itself dead); a fresh initialize() is what
    // actually revives it, so a "permanent" error still restarts, just
    // through that heavier path instead of giving up on standby entirely.
    if (error.permanent) _needsReinitialize = true;
    if (_enabled) _scheduleRestart();
  }

  void _scheduleRestart() {
    _restartTimer?.cancel();
    // Android's on-device recognizer often ends a session after only a
    // second or two of silence (NO_SPEECH_DETECTED), which is expected, and
    // the mic is "deaf" until we restart it -- so for wake-word spotting we
    // want that gap as small as possible. But restarting too aggressively
    // (previously tried 60ms flat) can overwhelm the platform recognizer
    // service and leave it refusing to start new sessions at all, which is
    // worse than an occasional missed word. Back off the delay the longer
    // restarts keep failing, and reset to the fast path once one succeeds.
    _consecutiveRestartFailures = (_consecutiveRestartFailures + 1).clamp(0, 6);
    final delayMs = 300 * (1 << (_consecutiveRestartFailures - 1).clamp(0, 4));
    _restartTimer = Timer(Duration(milliseconds: delayMs), () {
      if (_enabled) unawaited(_restart());
    });
  }

  Future<void> _restart() async {
    if (!_enabled || _starting) return;
    if (_speech.isListening) await _speech.stop();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    if (!_enabled) return;
    if (_needsReinitialize) {
      _needsReinitialize = false;
      await initialize();
    }
    await start();
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
