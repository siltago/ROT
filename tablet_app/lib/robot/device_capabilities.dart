class DeviceCapabilities {
  const DeviceCapabilities({
    this.cameraFront = true,
    this.cameraBack = false,
    this.microphone = true,
    this.speaker = true,
    this.screen = true,
    this.accelerometer = true,
    this.gyroscope = true,
    this.localSpeechRecognition = true,
  });

  final bool cameraFront;
  final bool cameraBack;
  final bool microphone;
  final bool speaker;
  final bool screen;
  final bool accelerometer;
  final bool gyroscope;
  final bool localSpeechRecognition;

  List<String> toList() => [
        if (cameraFront) 'camera.front',
        if (cameraBack) 'camera.back',
        if (microphone) 'microphone',
        if (speaker) 'speaker',
        if (screen) 'screen',
        if (accelerometer) 'accelerometer',
        if (gyroscope) 'gyroscope',
        if (localSpeechRecognition) 'speech_recognition.local',
      ];
}
