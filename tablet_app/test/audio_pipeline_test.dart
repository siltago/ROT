import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:robot_tablet_app/devices/microphone/audio_pipeline.dart';

void main() {
  test('VAD calibrates ambient sound before enabling speech starts', () {
    const config = AudioPipelineConfig();
    final vad = AdaptiveVoiceActivityDetector(config);
    final ambient = Uint8List(1600);
    final bytes = ByteData.sublistView(ambient);
    for (var i = 0; i < ambient.length ~/ 2; i++) {
      bytes.setInt16(i * 2, i.isEven ? 300 : -300, Endian.little);
    }
    for (var i = 0; i < 20; i++) {
      expect(vad.analyze(ambient, TurnState.idle).vadState, VadState.silence);
    }
    final afterCalibration = vad.analyze(ambient, TurnState.idle);
    expect(afterCalibration.vadState, isNot(VadState.speech));
  });

  test('noise floor moves slowly upward and ignores speech', () {
    final floor = NoiseFloorEstimator(initialDb: -60);
    floor.update(-45, speech: false);
    expect(floor.value, closeTo(-59.82, 0.01));
    floor.update(-20, speech: true);
    expect(floor.value, closeTo(-59.82, 0.01));
  });

  test('turn detector confirms start and tolerates a short pause', () {
    const config = AudioPipelineConfig(
      speechStartConfirmation: Duration(milliseconds: 100),
      endTurnSilence: Duration(milliseconds: 700),
      postRoll: Duration(milliseconds: 100),
    );
    final detector = TurnDetector(config);
    expect(
        detector.update(VadState.speech, const Duration(milliseconds: 50))?.to,
        TurnState.preSpeech);
    final started =
        detector.update(VadState.speech, const Duration(milliseconds: 50));
    expect(started?.speechStarted, isTrue);
    detector.update(VadState.silence, const Duration(milliseconds: 300));
    expect(detector.state, TurnState.maybeEnd);
    detector.update(VadState.speech, const Duration(milliseconds: 50));
    expect(detector.state, TurnState.listening);
  });

  test('turn ends only after configured silence plus post roll', () {
    const config = AudioPipelineConfig(
      speechStartConfirmation: Duration(milliseconds: 50),
      endTurnSilence: Duration(milliseconds: 100),
      postRoll: Duration(milliseconds: 50),
    );
    final detector = TurnDetector(config);
    detector.update(VadState.speech, const Duration(milliseconds: 50));
    detector.update(VadState.speech, const Duration(milliseconds: 50));
    detector.update(VadState.silence, const Duration(milliseconds: 100));
    expect(detector.state, TurnState.maybeEnd);
    final ended =
        detector.update(VadState.silence, const Duration(milliseconds: 50));
    expect(ended?.speechEnded, isTrue);
    expect(detector.state, TurnState.idle);
  });

  test('pre-roll keeps only the configured window', () {
    const config =
        AudioPipelineConfig(chunkMs: 50, preRoll: Duration(milliseconds: 150));
    final buffer = PreRollBuffer(config);
    for (var i = 0; i < 5; i++) {
      buffer.add(Uint8List.fromList([i]));
    }
    expect(buffer.drain().map((frame) => frame.first), [2, 3, 4]);
  });
}
