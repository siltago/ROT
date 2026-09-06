import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:robot_tablet_app/devices/microphone/microphone_service.dart';

void main() {
  test('VAD emits one start and one end after sustained silence', () {
    final detector = VoiceActivityDetector(
      threshold: 0.1,
      endSilence: const Duration(milliseconds: 500),
    );
    final start = DateTime(2025);

    expect(detector.update(0.2, start), SpeechEvent.started);
    expect(detector.update(0.3, start.add(const Duration(milliseconds: 50))),
        isNull);
    expect(detector.update(0, start.add(const Duration(milliseconds: 400))),
        isNull);
    expect(
      detector.update(0, start.add(const Duration(milliseconds: 600))),
      SpeechEvent.ended,
    );
  });

  test('PCM RMS reports silence and a normalized signal', () {
    expect(MicrophoneService.pcm16Rms(Uint8List(8)), 0);
    final signal = Uint8List.fromList([0xff, 0x7f, 0x00, 0x80]);
    expect(MicrophoneService.pcm16Rms(signal), closeTo(1, 0.001));
  });
}
