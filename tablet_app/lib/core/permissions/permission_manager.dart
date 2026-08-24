import 'package:permission_handler/permission_handler.dart';

class PermissionManager {
  Future<bool> requestCameraAndMicrophone() async {
    final cameraStatus = await Permission.camera.request();
    final microphoneStatus = await Permission.microphone.request();

    return (cameraStatus.isGranted || cameraStatus.isLimited) &&
        (microphoneStatus.isGranted || microphoneStatus.isLimited);
  }
}
