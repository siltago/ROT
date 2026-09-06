import 'package:flutter_test/flutter_test.dart';
import 'package:robot_tablet_app/robot/presentation_scene.dart';

void main() {
  test('temporary scene parses its semantic recipe', () {
    final scene = PresentationScene.fromPayload({
      'kind': 'weather',
      'variant': 'rain',
      'duration_ms': 10000,
      'persistent': false,
      'data': {'temperature': 21, 'condition': 'rain'},
    });

    expect(scene.kind, 'weather');
    expect(scene.variant, 'rain');
    expect(scene.duration, const Duration(seconds: 10));
    expect(scene.persistent, isFalse);
    expect(scene.data['temperature'], 21);
  });

  test('persistent scenes do not require a duration', () {
    final scene = PresentationScene.fromPayload({
      'kind': 'music',
      'persistent': true,
      'data': {'title': 'Song'},
    });

    expect(scene.persistent, isTrue);
    expect(scene.duration, isNull);
  });
}
