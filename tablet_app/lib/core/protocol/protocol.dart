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
      timestamp: (json['timestamp'] as num?)?.toInt() ??
          DateTime.now().millisecondsSinceEpoch,
      payload: rawPayload is Map
          ? Map<String, dynamic>.from(rawPayload)
          : const <String, dynamic>{},
    );
  }
}

class RobotMessageFactory {
  static RobotMessage audioStreamStart({
    required String deviceId,
    required String streamId,
    required int sampleRate,
    required int channels,
    required int chunkMs,
  }) =>
      RobotMessage(
        version: 1,
        type: 'audio_stream_start',
        deviceId: deviceId,
        timestamp: DateTime.now().millisecondsSinceEpoch,
        payload: {
          'stream_id': streamId,
          'format': {
            'encoding': 'pcm_s16le',
            'sample_rate': sampleRate,
            'channels': channels,
            'bit_depth': 16,
            'chunk_ms': chunkMs,
          },
        },
      );

  static RobotMessage audioStreamEnd({
    required String deviceId,
    required String streamId,
  }) =>
      RobotMessage(
        version: 1,
        type: 'audio_stream_end',
        deviceId: deviceId,
        timestamp: DateTime.now().millisecondsSinceEpoch,
        payload: {'stream_id': streamId},
      );

  static RobotMessage audioStreamCancel({
    required String deviceId,
    required String streamId,
    required String reason,
  }) =>
      RobotMessage(
        version: 1,
        type: 'audio_stream_cancel',
        deviceId: deviceId,
        timestamp: DateTime.now().millisecondsSinceEpoch,
        payload: {'stream_id': streamId, 'reason': reason},
      );

  /// Tells the brain the tablet has actually finished playing the last
  /// speech (greeting or reply) and resumed its mic -- the real end of a
  /// turn, so the brain doesn't have to guess/estimate how long that took
  /// before arming its wake-inactivity timer or moving on.
  static RobotMessage speechPlaybackDone({required String deviceId}) =>
      RobotMessage(
        version: 1,
        type: 'speech_playback_done',
        deviceId: deviceId,
        timestamp: DateTime.now().millisecondsSinceEpoch,
        payload: const {},
      );

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

  static RobotMessage speechStarted({
    required String deviceId,
    String? streamId,
  }) {
    return RobotMessage(
      version: 1,
      type: 'speech_started',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: streamId == null ? null : {'stream_id': streamId},
    );
  }

  static RobotMessage speechEnded({
    required String deviceId,
    String? streamId,
  }) {
    return RobotMessage(
      version: 1,
      type: 'speech_ended',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: streamId == null ? null : {'stream_id': streamId},
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

  /// Which idle self-entertainment vignette (if any) is currently
  /// showing -- lets the backend's cognition tick actually respond to
  /// what's on screen (resting/coffee speeds up energy recovery, the
  /// active cluster relieves boredom -- see api/server.py's
  /// _ACTIVE_IDLE_KINDS/_RESTING_IDLE_KINDS) instead of the vignette
  /// being purely cosmetic. [kind] is null when nothing's showing.
  /// Tells the backend the tablet's current hardware state (volume and
  /// brightness, 0..100) so Bob can answer questions about it and reason
  /// about adjusting it -- sent on connect and after every device_control.
  static RobotMessage deviceState({
    required String deviceId,
    required int volume,
    required int brightness,
  }) {
    return RobotMessage(
      version: 1,
      type: 'device_state',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {'volume': volume, 'brightness': brightness},
    );
  }

  static RobotMessage idleActivityReport({
    required String deviceId,
    required String? kind,
  }) {
    return RobotMessage(
      version: 1,
      type: 'idle_activity_report',
      deviceId: deviceId,
      timestamp: DateTime.now().millisecondsSinceEpoch,
      payload: {'kind': kind},
    );
  }
}
