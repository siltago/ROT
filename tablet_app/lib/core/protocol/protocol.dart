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
    return RobotMessage(
      version: (json['version'] as num?)?.toInt() ?? 1,
      type: (json['type'] ?? '').toString(),
      deviceId: (json['device_id'] ?? 'tablet_001').toString(),
      timestamp: (json['timestamp'] as num?)?.toInt() ?? DateTime.now().millisecondsSinceEpoch,
      payload: (json['payload'] as Map<String, dynamic>?) ?? const {},
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
