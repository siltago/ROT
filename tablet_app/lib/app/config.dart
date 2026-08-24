class AppConfig {
  static const String defaultBrainUrl = String.fromEnvironment(
    'ROBOT_BRAIN_URL',
    defaultValue: 'ws://10.0.2.2:8000/ws/device',
  );
  static const String brainUrlPreferenceKey = 'brain_websocket_url';
  static const String deviceId = 'tablet_001';
  static const Duration reconnectDelay = Duration(seconds: 2);
  static const Duration maxReconnectDelay = Duration(seconds: 30);
  static const Duration connectionTimeout = Duration(seconds: 8);
  static const int micChunkMs = 50;
  static const int audioSampleRate = 16000;
  static const double speechThreshold = 0.08;
  static const Duration speechEndSilence = Duration(milliseconds: 650);
  static const int cameraWidth = 640;
  static const int cameraHeight = 480;
  static const int observationFps = 5;
}
