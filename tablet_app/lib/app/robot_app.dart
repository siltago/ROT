import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:logger/logger.dart';

import '../core/connection/robot_connection.dart';
import '../core/permissions/permission_manager.dart';
import '../core/protocol/protocol.dart';
import '../devices/audio/audio_output_service.dart';
import '../devices/camera/camera_service.dart';
import '../devices/microphone/microphone_service.dart';
import '../robot/device_capabilities.dart';
import '../robot/robot_display_state.dart';
import '../ui/debug_panel.dart';
import '../ui/robot_face_widget.dart';

class RobotApp extends StatefulWidget {
  const RobotApp({super.key});

  @override
  State<RobotApp> createState() => _RobotAppState();
}

class _RobotAppState extends State<RobotApp> {
  final RobotConnection _connection = RobotConnection();
  final CameraService _cameraService = CameraService();
  final MicrophoneService _microphoneService = MicrophoneService();
  final AudioOutputService _audioOutputService = AudioOutputService();
  final PermissionManager _permissionManager = PermissionManager();
  final Logger _logger = Logger();

  RobotDisplayState _robotState = RobotDisplayState.idle;
  String _expression = 'neutral';
  bool _debugVisible = false;
  bool _connected = false;
  bool _speechDetected = false;
  double _microphoneLevel = 0.0;
  bool _cameraReady = false;

  @override
  void initState() {
    super.initState();
    _initialize();
  }

  Future<void> _initialize() async {
    final permissionsGranted = await _permissionManager.requestCameraAndMicrophone();
    if (!permissionsGranted) {
      setState(() {
        _robotState = RobotDisplayState.error;
      });
      return;
    }

    try {
      await _cameraService.initialize(frontCamera: true);
      await _cameraService.startPreview();
      setState(() {
        _cameraReady = true;
      });
    } catch (_) {
      _logger.e('Camera initialization failed');
    }

    try {
      await _microphoneService.start();
      _microphoneService.levelStream.listen((level) {
        if (!mounted) return;
        setState(() {
          _microphoneLevel = level;
          _speechDetected = level > 0.15;
        });
      });
    } catch (_) {
      _logger.e('Microphone initialization failed');
    }

    await _connect();
  }

  Future<void> _connect() async {
    try {
      await _connection.connect('ws://192.168.1.10:8000/ws/device');
      final deviceId = 'tablet_001';
      _connection.sendMessage(
        RobotMessageFactory.hello(
          deviceId: deviceId,
          capabilities: const DeviceCapabilities().toList(),
        ),
      );
      _connection.onMessage.listen((message) {
        _handleIncomingMessage(message);
      });
      setState(() {
        _connected = true;
      });
    } catch (error) {
      _logger.e('WebSocket connection failed: $error');
      setState(() {
        _connected = false;
        _robotState = RobotDisplayState.offline;
      });
      unawaited(
        Future<void>.delayed(const Duration(seconds: 2), () async {
          await _connect();
        }),
      );
    }
  }

  void _handleIncomingMessage(Map<String, dynamic> json) {
    final message = RobotMessage.fromJson(json);
    switch (message.type) {
      case 'set_state':
        final stateName = (message.payload?['state'] ?? 'IDLE').toString();
        final state = _parseDisplayState(stateName);
        setState(() {
          _robotState = state;
        });
        break;
      case 'set_expression':
        final expression = (message.payload?['expression'] ?? 'neutral').toString();
        setState(() {
          _expression = expression;
        });
        break;
      case 'speak':
        final payload = message.payload ?? {};
        final text = (payload['text'] ?? '').toString();
        if (text.isNotEmpty) {
          _audioOutputService.speak(text);
          setState(() {
            _robotState = RobotDisplayState.speaking;
          });
        }
        break;
      case 'stop_speaking':
        _audioOutputService.stop();
        setState(() {
          _robotState = RobotDisplayState.idle;
        });
        break;
      case 'ping':
        _connection.sendMessage(
          RobotMessage(
            version: 1,
            type: 'device_status',
            deviceId: 'tablet_001',
            timestamp: DateTime.now().millisecondsSinceEpoch,
            payload: {
              'battery': 90,
              'wifi': 'connected',
              'state': _robotState.label,
            },
          ),
        );
        break;
      default:
        break;
    }
  }

  RobotDisplayState _parseDisplayState(String value) {
    final normalized = value.trim().toUpperCase();
    switch (normalized) {
      case 'OFFLINE':
        return RobotDisplayState.offline;
      case 'LISTENING':
        return RobotDisplayState.listening;
      case 'THINKING':
        return RobotDisplayState.thinking;
      case 'ACTING':
        return RobotDisplayState.acting;
      case 'SPEAKING':
        return RobotDisplayState.speaking;
      case 'ERROR':
        return RobotDisplayState.error;
      case 'SLEEPING':
        return RobotDisplayState.sleeping;
      case 'IDLE':
      default:
        return RobotDisplayState.idle;
    }
  }

  @override
  Widget build(BuildContext context) {
    final statusColor = _connected ? Colors.green : Colors.red;

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0B1020),
      ),
      home: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              Positioned.fill(
                child: GestureDetector(
                  onTap: () {
                    setState(() {
                      _debugVisible = !_debugVisible;
                    });
                  },
                  child: Column(
                    children: [
                      Expanded(
                        child: Center(
                          child: RobotFaceWidget(
                            expression: _expression,
                            state: _robotState,
                            microphoneLevel: _microphoneLevel,
                            speechDetected: _speechDetected,
                            cameraPreview: _cameraService.previewWidget,
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.all(12),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              decoration: BoxDecoration(
                                color: statusColor.withOpacity(0.15),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: Text(
                                _connected ? 'ONLINE' : 'OFFLINE',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                            FloatingActionButton.small(
                              onPressed: () {
                                setState(() {
                                  _debugVisible = !_debugVisible;
                                });
                              },
                              child: const Icon(Icons.bug_report_outlined),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (_debugVisible)
                Align(
                  alignment: Alignment.topRight,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: DebugPanel(
                      connected: _connected,
                      robotState: _robotState,
                      expression: _expression,
                      speechDetected: _speechDetected,
                      microphoneLevel: _microphoneLevel,
                      cameraReady: _cameraReady,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _connection.dispose();
    _microphoneService.stop();
    _cameraService.dispose();
    _audioOutputService.stop();
    super.dispose();
  }
}
