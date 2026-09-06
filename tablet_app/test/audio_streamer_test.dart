import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:robot_tablet_app/devices/microphone/audio_streamer.dart';

void main() {
  test('audio input mode preserves legacy as safe fallback', () {
    expect(
      AudioInputMode.parse('androidSpeechRecognizer'),
      AudioInputMode.androidSpeechRecognizer,
    );
    expect(AudioInputMode.parse('pcmStreaming'), AudioInputMode.pcmStreaming);
    expect(AudioInputMode.parse('invalid'),
        AudioInputMode.androidSpeechRecognizer);
  });

  test('binary frame contains magic, sequence and unchanged PCM', () {
    final frame = AudioStreamer.frameAudio(42, Uint8List.fromList([1, 2, 3]));
    expect(frame.sublist(0, 4), [0x52, 0x42, 0x41, 0x31]);
    expect(ByteData.sublistView(frame).getUint32(4), 42);
    expect(frame.sublist(8), [1, 2, 3]);
  });
}
