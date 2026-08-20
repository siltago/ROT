import 'package:flutter_tts/flutter_tts.dart';

class AudioOutputService {
  final FlutterTts _tts = FlutterTts();

  Future<void> speak(String text) async {
    await _tts.setLanguage('pt-BR');
    await _tts.speak(text);
  }

  Future<void> stop() async {
    await _tts.stop();
  }
}
