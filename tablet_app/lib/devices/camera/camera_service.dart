import 'dart:async';
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';

class CapturedCameraFrame {
  const CapturedCameraFrame({
    required this.bytes,
    required this.width,
    required this.height,
  });

  final List<int> bytes;
  final int width;
  final int height;
}

class CameraService {
  CameraController? _controller;
  CameraDescription? _frontCamera;
  final StreamController<Offset?> _facePositions = StreamController.broadcast();
  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
      performanceMode: FaceDetectorMode.fast,
      enableTracking: true,
      minFaceSize: 0.12,
    ),
  );
  bool _processingFrame = false;
  DateTime _lastDetection = DateTime.fromMillisecondsSinceEpoch(0);
  Offset _smoothedFace = const Offset(0.5, 0.5);
  Offset _lastEmittedFace = const Offset(0.5, 0.5);
  int _missedDetections = 0;

  Stream<Offset?> get facePositions => _facePositions.stream;

  Widget get previewWidget {
    if (_controller == null || !_controller!.value.isInitialized) {
      return const Center(
        child:
            Icon(Icons.videocam_off_outlined, size: 48, color: Colors.white70),
      );
    }
    return CameraPreview(_controller!);
  }

  Future<void> initialize({required bool frontCamera}) async {
    final cameras = await availableCameras();
    final selected = cameras.firstWhere(
      (camera) => frontCamera
          ? camera.lensDirection == CameraLensDirection.front
          : camera.lensDirection == CameraLensDirection.back,
      orElse: () => cameras.first,
    );
    _frontCamera = selected;
    _controller = CameraController(
      selected,
      ResolutionPreset.medium,
      enableAudio: false,
      imageFormatGroup: Platform.isAndroid
          ? ImageFormatGroup.nv21
          : ImageFormatGroup.bgra8888,
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
    if (!_controller!.value.isStreamingImages) {
      await _controller!.startImageStream(_detectFace);
    }
  }

  Future<void> _detectFace(CameraImage image) async {
    final now = DateTime.now();
    if (_processingFrame ||
        now.difference(_lastDetection) < const Duration(milliseconds: 450)) {
      return;
    }
    _processingFrame = true;
    _lastDetection = now;
    try {
      final format = InputImageFormatValue.fromRawValue(image.format.raw);
      final rotation = InputImageRotationValue.fromRawValue(
        _frontCamera?.sensorOrientation ?? 0,
      );
      if (format == null || rotation == null || image.planes.length != 1) {
        return;
      }
      final plane = image.planes.first;
      final input = InputImage.fromBytes(
        bytes: plane.bytes,
        metadata: InputImageMetadata(
          size: Size(image.width.toDouble(), image.height.toDouble()),
          rotation: rotation,
          format: format,
          bytesPerRow: plane.bytesPerRow,
        ),
      );
      final faces = await _faceDetector.processImage(input);
      if (_facePositions.isClosed) return;
      if (faces.isEmpty) {
        _missedDetections++;
        if (_missedDetections >= 5) {
          _smoothedFace = const Offset(0.5, 0.5);
          _emitFaceIfMoved(_smoothedFace);
        }
        return;
      }
      _missedDetections = 0;
      final face = faces.reduce(
        (current, candidate) =>
            candidate.boundingBox.width > current.boundingBox.width
                ? candidate
                : current,
      );
      final center = face.boundingBox.center;
      final x = (1 - center.dx / image.width).clamp(0.0, 1.0).toDouble();
      final y = (center.dy / image.height).clamp(0.0, 1.0).toDouble();
      final detected = Offset(x, y);
      const smoothing = 0.16;
      _smoothedFace = Offset(
        _smoothedFace.dx + (detected.dx - _smoothedFace.dx) * smoothing,
        _smoothedFace.dy + (detected.dy - _smoothedFace.dy) * smoothing,
      );
      _emitFaceIfMoved(_smoothedFace);
    } catch (_) {
      // A malformed camera frame must not interrupt preview or conversation.
    } finally {
      _processingFrame = false;
    }
  }

  void _emitFaceIfMoved(Offset position) {
    const deadZone = 0.025;
    final dx = position.dx - _lastEmittedFace.dx;
    final dy = position.dy - _lastEmittedFace.dy;
    if (dx.abs() < deadZone && dy.abs() < deadZone) return;
    _lastEmittedFace = position;
    if (!_facePositions.isClosed) _facePositions.add(position);
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

  Future<CapturedCameraFrame> captureFrame() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      throw StateError('Camera not initialized');
    }
    final wasStreaming = controller.value.isStreamingImages;
    if (wasStreaming) await controller.stopImageStream();
    final image = await controller.takePicture();
    if (wasStreaming) await controller.startImageStream(_detectFace);
    final bytes = await image.readAsBytes();
    return CapturedCameraFrame(
      bytes: bytes,
      width: controller.value.previewSize?.width.round() ?? 0,
      height: controller.value.previewSize?.height.round() ?? 0,
    );
  }

  void dispose() {
    if (_controller?.value.isStreamingImages == true) {
      unawaited(_controller?.stopImageStream());
    }
    unawaited(_faceDetector.close());
    unawaited(_facePositions.close());
    _controller?.dispose();
    _controller = null;
  }
}
