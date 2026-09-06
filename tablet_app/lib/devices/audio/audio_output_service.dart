import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// Speaks either via the device's native TTS (flutter_tts, today's default)
/// or by playing already-synthesized audio bytes (e.g. from a Piper voice
/// running on the brain) -- callers don't need to know which path is live;
/// both report through the same onStarted/onCompleted/onCancelled hooks so
/// the rest of the app (pausing the mic while the robot talks) never changes.
class AudioOutputService {
  final FlutterTts _tts = FlutterTts();
  final AudioPlayer _player = AudioPlayer();
  bool _initialized = false;
  void Function()? _onStarted;
  void Function()? _onCompleted;

  Future<void> initialize({
    void Function()? onStarted,
    void Function()? onCompleted,
    void Function()? onCancelled,
  }) async {
    if (_initialized) return;
    _onStarted = onStarted;
    _onCompleted = onCompleted;
    await _tts.setLanguage('pt-BR');
    await _tts.awaitSpeakCompletion(true);
    _tts.setStartHandler(() => onStarted?.call());
    _tts.setCompletionHandler(() => onCompleted?.call());
    _tts.setCancelHandler(() => onCancelled?.call());
    _player.onPlayerComplete.listen((_) => _onCompleted?.call());
    _initialized = true;
  }

  Future<void> speak(String text) async {
    if (!_initialized) await initialize();
    await _tts.speak(text);
  }

  /// Plays a complete audio file's bytes (e.g. a Piper-synthesized WAV)
  /// instead of asking the device's own TTS to say the text.
  Future<void> playBytes(Uint8List audio) async {
    if (!_initialized) await initialize();
    _onStarted?.call();
    await _player.play(BytesSource(audio));
  }

  Future<void> stop() async {
    await _tts.stop();
    await _player.stop();
  }
}
