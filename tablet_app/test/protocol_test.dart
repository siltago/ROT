import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:robot_tablet_app/core/protocol/protocol.dart';

void main() {
  test('message round-trips using the versioned envelope', () {
    const original = RobotMessage(
      version: 1,
      type: 'set_state',
      deviceId: 'tablet_test',
      timestamp: 123,
      payload: {'state': 'LISTENING'},
    );

    final decoded = RobotMessage.fromJson(
      jsonDecode(jsonEncode(original.toJson())) as Map<String, dynamic>,
    );

    expect(decoded.version, 1);
    expect(decoded.type, 'set_state');
    expect(decoded.deviceId, 'tablet_test');
    expect(decoded.payload?['state'], 'LISTENING');
  });

  test('audio chunk uses pcm16 metadata and base64 payload', () {
    final message = RobotMessageFactory.audioChunk(
      deviceId: 'tablet_test',
      data: Uint8List.fromList([1, 2, 3, 4]),
    );

    expect(message.type, 'audio_chunk');
    expect(message.payload?['encoding'], 'pcm16');
    expect(message.payload?['sample_rate'], 16000);
    expect(
        base64Decode(message.payload?['data_base64'] as String), [1, 2, 3, 4]);
  });
}
