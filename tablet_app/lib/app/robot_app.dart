import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:logger/logger.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/connection/robot_connection.dart';
import '../core/permissions/permission_manager.dart';
import '../core/protocol/protocol.dart';
import '../devices/audio/audio_output_service.dart';
import '../devices/camera/camera_service.dart';
import '../devices/microphone/speech_recognition_service.dart';
import '../robot/device_capabilities.dart';
import '../robot/robot_display_state.dart';
import '../ui/debug_panel.dart';
import '../ui/robot_face_widget.dart';
import '../ui/settings_screen.dart';
import 'config.dart';

class RobotApp extends StatefulWidget {
  const RobotApp({super.key});

  @override
  State<RobotApp> createState() => _RobotAppState();
}

class _RobotAppState extends State<RobotApp> {
  final RobotConnection _connection = RobotConnection();
  final CameraService _camera = CameraService();
  final SpeechRecognitionService _speechRecognition = SpeechRecognitionService();
  final AudioOutputService _audioOutput = AudioOutputService();
  final PermissionManager _permissions = PermissionManager();
  final Logger _logger = Logger();
  final List<StreamSubscription<dynamic>> _subscriptions = [];

  RobotDisplayState _robotState = RobotDisplayState.offline;
  String _expression = 'neutral';
  String _brainUrl = AppConfig.defaultBrainUrl;
  bool _debugVisible = false;
  bool _connected = false;
  bool _speechDetected = false;
  double _microphoneLevel = 0;
  bool _cameraReady = false;
  bool _microphoneReady = false;
  String _lastTranscript = '';
  String _lastReply = 'Estou pronto para ouvir.';
  Timer? _speechCommitTimer;
  String _pendingTranscript = '';
  String _lastSubmittedTranscript = '';
  DateTime? _lastSubmittedAt;
  Offset? _trackedFace;

  @override
  void initState() {
    super.initState();
    unawaited(_initialize());
  }

  Future<void> _initialize() async {
    final preferences = await SharedPreferences.getInstance();
    _brainUrl = preferences.getString(AppConfig.brainUrlPreferenceKey) ??
        AppConfig.defaultBrainUrl;
    _bindStreams();
    await _audioOutput.initialize(
      onStarted: () {
        _setRobotState(RobotDisplayState.speaking);
        unawaited(_speechRecognition.stop());
      },
      onCompleted: () {
        _setRobotState(RobotDisplayState.idle);
        unawaited(_speechRecognition.start());
      },
      onCancelled: () {
        _setRobotState(RobotDisplayState.idle);
        unawaited(_speechRecognition.start());
      },
    );

    if (!await _permissions.requestCameraAndMicrophone()) {
      _setRobotState(RobotDisplayState.error);
      return;
    }
    await Future.wait([_startCamera(), _startMicrophone()]);
    await _connection.connect(_brainUrl);
  }

  void _bindStreams() {
    _subscriptions.add(_connection.onMessage.listen(_handleIncomingMessage));
    _subscriptions.add(_connection.onStatus.listen((status) {
      if (!mounted) return;
      final connected = status == ConnectionStatus.connected;
      setState(() {
        _connected = connected;
        if (!connected) _robotState = RobotDisplayState.offline;
      });
      if (connected) {
        _connection.sendMessage(
          RobotMessageFactory.hello(
            deviceId: AppConfig.deviceId,
            capabilities: const DeviceCapabilities().toList(),
          ),
        );
      }
    }));
    _subscriptions.add(_speechRecognition.levels.listen((level) {
      if (!mounted) return;
      setState(() => _microphoneLevel = level);
    }));
    _subscriptions.add(_camera.facePositions.listen((position) {
      if (!mounted) return;
      setState(() => _trackedFace = position);
    }));
    _subscriptions.add(_speechRecognition.listening.listen((listening) {
      if (!mounted) return;
      setState(() => _speechDetected = listening);
    }));
    _subscriptions.add(_speechRecognition.results.listen((result) {
      if (!mounted) return;
      final text = result.text.trim();
      if (text.isEmpty) return;
      final transcriptChanged = text != _pendingTranscript;
      if (transcriptChanged) {
        _pendingTranscript = text;
        setState(() => _lastTranscript = text);
      }
      if (!result.isFinal && !transcriptChanged) return;
      _speechCommitTimer?.cancel();
      if (result.isFinal) {
        _submitRecognizedSpeech();
      } else {
        _speechCommitTimer = Timer(
          const Duration(milliseconds: 2800),
          _submitRecognizedSpeech,
        );
      }
    }));
  }

  void _submitRecognizedSpeech() {
    final text = _pendingTranscript.trim();
    if (!mounted || text.isEmpty) return;
    final now = DateTime.now();
    final recentlySubmitted = text == _lastSubmittedTranscript &&
        _lastSubmittedAt != null &&
        now.difference(_lastSubmittedAt!) < const Duration(seconds: 3);
    if (recentlySubmitted) return;
    _lastSubmittedTranscript = text;
    _lastSubmittedAt = now;
    _speechCommitTimer?.cancel();
    unawaited(_speechRecognition.stop());
    setState(() => _lastReply = 'Pensando...');
      _setRobotState(RobotDisplayState.thinking);
      _connection.sendMessage(
        RobotMessageFactory.recognizedSpeech(
          deviceId: AppConfig.deviceId,
          text: text,
          isFinal: true,
        ),
      );
  }

  Future<void> _startCamera() async {
    try {
      await _camera.initialize(frontCamera: true);
      await _camera.startPreview();
      if (mounted) setState(() => _cameraReady = true);
    } catch (error, stackTrace) {
      _logger.e('Camera initialization failed', error: error, stackTrace: stackTrace);
    }
  }

  Future<void> _startMicrophone() async {
    try {
      final available = await _speechRecognition.initialize();
      if (!available) throw StateError('Android speech recognition unavailable');
      await _speechRecognition.start();
      if (mounted) setState(() => _microphoneReady = available);
    } catch (error, stackTrace) {
      _logger.e('Microphone initialization failed', error: error, stackTrace: stackTrace);
    }
  }

  void _handleIncomingMessage(Map<String, dynamic> json) {
    final message = RobotMessage.fromJson(json);
    switch (message.type) {
      case 'set_state':
        _setRobotState(_parseDisplayState('${message.payload?['state'] ?? 'IDLE'}'));
        return;
      case 'set_expression':
      case 'expression':
        final value = message.payload?['expression'] ??
            message.payload?['value'] ??
            json['value'] ??
            'neutral';
        if (mounted) setState(() => _expression = value.toString().toLowerCase());
        return;
      case 'speak':
        final text = '${message.payload?['text'] ?? ''}'.trim();
        if (text.isNotEmpty) unawaited(_audioOutput.speak(text));
        return;
      case 'stop_speaking':
        unawaited(_audioOutput.stop());
        return;
      case 'show_transcript':
        final text = '${message.payload?['text'] ?? ''}'.trim();
        if (text.isNotEmpty && mounted) setState(() => _lastTranscript = text);
        return;
      case 'show_message':
        final text = '${message.payload?['message'] ?? ''}'.trim();
        if (text.isNotEmpty && mounted) setState(() => _lastReply = text);
        return;
      case 'ping':
        _connection.sendMessage(
          RobotMessageFactory.deviceStatus(
            deviceId: AppConfig.deviceId,
            state: _robotState,
          ),
        );
        return;
      default:
        return;
    }
  }

  Future<void> _captureAndSendFrame() async {
    try {
      final frame = await _camera.captureFrame();
      _connection.sendMessage(
        RobotMessageFactory.cameraFrame(
          deviceId: AppConfig.deviceId,
          data: Uint8List.fromList(frame.bytes),
          width: frame.width,
          height: frame.height,
        ),
      );
    } catch (error, stackTrace) {
      _logger.e('Camera capture failed', error: error, stackTrace: stackTrace);
    }
  }

  Future<void> _openSettings() async {
    final newUrl = await Navigator.of(context).push<String>(
      MaterialPageRoute(builder: (_) => SettingsScreen(initialUrl: _brainUrl)),
    );
    if (newUrl == null || newUrl == _brainUrl) return;
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(AppConfig.brainUrlPreferenceKey, newUrl);
    if (mounted) setState(() => _brainUrl = newUrl);
    await _connection.connect(newUrl);
  }

  void _setRobotState(RobotDisplayState state) {
    if (mounted) setState(() => _robotState = state);
  }

  RobotDisplayState _parseDisplayState(String value) {
    return RobotDisplayState.values.firstWhere(
      (state) => state.label == value.trim().toUpperCase(),
      orElse: () => RobotDisplayState.idle,
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: const Color(0xFF070B16),
      ),
      home: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              Positioned.fill(
                child: GestureDetector(
                  onLongPress: () => setState(() => _debugVisible = !_debugVisible),
                  child: RobotFaceWidget(
                    expression: _expression,
                    state: _robotState,
                    microphoneLevel: _microphoneLevel,
                    speechDetected: _speechDetected,
                    cameraPreview: _camera.previewWidget,
                    trackedFace: _trackedFace,
                  ),
                ),
              ),
              Positioned(
                left: 16,
                bottom: 16,
                child: _StatusPill(connected: _connected),
              ),
              Positioned(
                left: 140,
                right: 140,
                bottom: 14,
                child: _ConversationCard(
                  transcript: _lastTranscript,
                  reply: _lastReply,
                ),
              ),
              Positioned(
                right: 12,
                bottom: 8,
                child: IconButton(
                  tooltip: 'Diagnóstico',
                  onPressed: () => setState(() => _debugVisible = !_debugVisible),
                  icon: const Icon(Icons.bug_report_outlined),
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
                      microphoneReady: _microphoneReady,
                      brainUrl: _brainUrl,
                      onCaptureFrame: () => unawaited(_captureAndSendFrame()),
                      onOpenSettings: () => unawaited(_openSettings()),
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
    _speechCommitTimer?.cancel();
    for (final subscription in _subscriptions) {
      unawaited(subscription.cancel());
    }
    unawaited(_connection.dispose());
    unawaited(_speechRecognition.dispose());
    _camera.dispose();
    unawaited(_audioOutput.stop());
    super.dispose();
  }
}

class _ConversationCard extends StatelessWidget {
  const _ConversationCard({required this.transcript, required this.reply});

  final String transcript;
  final String reply;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxHeight: 145),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xDD111827),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white24),
      ),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (transcript.isNotEmpty)
              Text('Você: $transcript', style: const TextStyle(color: Colors.white60)),
            const SizedBox(height: 5),
            Text(
              reply,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.connected});
  final bool connected;

  @override
  Widget build(BuildContext context) {
    final color = connected ? Colors.greenAccent : Colors.redAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        connected ? 'ROBOT ONLINE' : 'OFFLINE • RECONECTANDO',
        style: TextStyle(color: color, fontWeight: FontWeight.w700),
      ),
    );
  }
}
