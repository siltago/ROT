class AppConfig {
  static const String defaultBrainUrl = 'ws://192.168.1.10:8000/ws/device';
  static const Duration reconnectDelay = Duration(seconds: 2);
  static const int micChunkMs = 50;
  static const int audioSampleRate = 16000;
  static const int cameraWidth = 640;
  static const int cameraHeight = 480;
  static const int observationFps = 5;
}
