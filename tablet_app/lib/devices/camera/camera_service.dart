import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

class CameraService {
  CameraController? _controller;
  CameraDescription? _frontCamera;

  Widget get previewWidget {
    if (_controller == null || !_controller!.value.isInitialized) {
      return const Center(
        child: Icon(Icons.videocam_off_outlined, size: 48, color: Colors.white70),
      );
    }
    return CameraPreview(_controller!);
  }

  Future<void> initialize({required bool frontCamera}) async {
    final cameras = await availableCameras();
    final selected = cameras.firstWhere(
      (camera) => frontCamera ? camera.lensDirection == CameraLensDirection.front : camera.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    _frontCamera = selected;
    _controller = CameraController(
      selected,
      ResolutionPreset.medium,
      enableAudio: false,
    );
    await _controller!.initialize();
  }

  Future<void> startPreview() async {
    if (_controller == null) {
      throw StateError('Camera not initialized');
    }
    if (!_controller!.value.isInitialized) {
      await initialize(frontCamera: true);
    }
    await _controller!.resumePreview();
  }

  Future<void> switchCamera() async {
    if (_controller == null) return;
    final cameras = await availableCameras();
    final next = cameras.firstWhere(
      (camera) => camera.name != _frontCamera?.name,
      orElse: () => cameras.first,
    );
    _frontCamera = next;
    await _controller!.setDescription(next);
  }

  void dispose() {
    _controller?.dispose();
    _controller = null;
  }
}
