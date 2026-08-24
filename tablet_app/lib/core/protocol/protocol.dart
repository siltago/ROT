import 'dart:convert';
import 'dart:typed_data';

import '../../robot/robot_display_state.dart';

class RobotMessage {
  const RobotMessage({
    required this.version,
    required this.type,
    required this.deviceId,
    required this.timestamp,
    this.payload,
  });

  final int version;
  final String type;
  final String deviceId;
  final int timestamp;
  final Map<String, dynamic>? payload;

  Map<String, dynamic> toJson() => {
        'version': version,
        'type': type,
        'device_id': deviceId,
        'timestamp': timestamp,
        if (payload != null) 'payload': payload,
      };

  factory RobotMessage.fromJson(Map<String, dynamic> json) {
    final rawPayload = json['payload'];
    return RobotMessage(
      version: (json['version'] as num?)?.toInt() ?? 1,
      type: (json['type'] ?? '').toString(),
      deviceId: (json['device_id'] ?? 'tablet_001').toString(),
      timestamp: (json['timestamp'] as num?)?.toInt() ?? DateTime.now().millisecondsSinceEpoch,
      payload: rawPayload is Map
          ? Map<String, dynamic>.from(rawPayload)
          : const <String, dynamic>{},
    );
  }
}

class RobotMessageFactory {
  static RobotMessage hello({
    required String deviceId,
    required List<String> capabilities,
  }) {
    return RobotMessage(
      version: 1,
      type: 'device_hello',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {
        'capabilities': capabilities,
      },
    );
  }

  static RobotMessage speechStarted({required String deviceId}) {
    return RobotMessage(
      version: 1,
      type: 'speech_started',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
    );
  }

  static RobotMessage speechEnded({required String deviceId}) {
    return RobotMessage(
      version: 1,
      type: 'speech_ended',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
    );
  }

  static RobotMessage recognizedSpeech({
    required String deviceId,
    required String text,
    required bool isFinal,
    double? confidence,
  }) {
    return RobotMessage(
      version: 1,
      type: 'recognized_speech',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {
        'text': text,
        'is_final': isFinal,
        if (confidence != null) 'confidence': confidence,
        'language': 'pt-BR',
        'source': 'android_speech_recognizer',
      },
    );
  }

  static RobotMessage audioChunk({
    required String deviceId,
    required Uint8List data,
    int sampleRate = 16000,
    int channels = 1,
    int chunkMs = 50,
  }) {
    return RobotMessage(
      version: 1,
      type: 'audio_chunk',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {
        'encoding': 'pcm16',
        'sample_rate': sampleRate,
        'channels': channels,
        'chunk_ms': chunkMs,
        'data_base64': base64Encode(data),
      },
    );
  }

  static RobotMessage cameraFrame({
    required String deviceId,
    required Uint8List data,
    required int width,
    required int height,
  }) {
    return RobotMessage(
      version: 1,
      type: 'camera_frame',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {
        'camera': 'front',
        'width': width,
        'height': height,
        'format': 'jpeg',
        'data_base64': base64Encode(data),
      },
    );
  }

  static RobotMessage deviceStatus({
    required String deviceId,
    required RobotDisplayState state,
    int? battery,
    String? wifi,
  }) {
    return RobotMessage(
      version: 1,
      type: 'device_status',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {
        'battery': battery ?? 100,
        'wifi': wifi ?? 'connected',
        'state': state.label,
      },
    );
  }
}
