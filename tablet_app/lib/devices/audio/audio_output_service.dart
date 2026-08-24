import 'package:flutter_tts/flutter_tts.dart';

class AudioOutputService {
  final FlutterTts _tts = FlutterTts();
  bool _initialized = false;

  Future<void> initialize({
    void Function()? onStarted,
    void Function()? onCompleted,
    void Function()? onCancelled,
  }) async {
    if (_initialized) return;
    await _tts.setLanguage('pt-BR');
    await _tts.awaitSpeakCompletion(true);
    _tts.setStartHandler(() => onStarted?.call());
    _tts.setCompletionHandler(() => onCompleted?.call());
    _tts.setCancelHandler(() => onCancelled?.call());
    _initialized = true;
  }

  Future<void> speak(String text) async {
    if (!_initialized) await initialize();
    await _tts.speak(text);
  }

  Future<void> stop() async {
    await _tts.stop();
  }
}
