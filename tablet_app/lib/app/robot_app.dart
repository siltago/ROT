import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:logger/logger.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/connection/robot_connection.dart';
import '../core/permissions/permission_manager.dart';
import '../core/protocol/protocol.dart';
import '../devices/audio/audio_output_service.dart';
import '../devices/camera/camera_service.dart';
import '../devices/device_controls.dart';
import '../devices/microphone/speech_recognition_service.dart';
import '../devices/microphone/audio_pipeline.dart';
import '../devices/microphone/audio_streamer.dart';
import '../devices/microphone/microphone_service.dart';
import '../robot/device_capabilities.dart';
import '../robot/robot_display_state.dart';
import '../robot/robot_mood.dart';
import '../robot/presentation_scene.dart';
import '../robot/wake_state.dart';
import '../ui/attributes_panel.dart';
import '../ui/debug_panel.dart';
import '../ui/idle_bored_overlay.dart';
import '../ui/idle_checkers_overlay.dart';
import '../ui/idle_chess_overlay.dart';
import '../ui/idle_coffee_overlay.dart';
import '../ui/idle_doodle_overlay.dart';
import '../ui/idle_feed_overlay.dart';
import '../ui/idle_humming_overlay.dart';
import '../ui/idle_reading_overlay.dart';
import '../ui/idle_resting_overlay.dart';
import '../ui/idle_snake_overlay.dart';
import '../ui/presentation_scene_widget.dart';
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
  final SpeechRecognitionService _speechRecognition =
      SpeechRecognitionService();

  /// Purely a display concern now (drives eye color, see [WakeState]): the
  /// backend decides -- and tells us via a `wake_state` message -- whether
  /// the wake word has been heard. Audio capture/STT run continuously
  /// either way; the brain is the one gating whether a transcript reaches
  /// the LLM (see api/server.py's AudioStreamCoordinator).
  WakeState _wakeState = WakeState.standby;

  /// True while the streaming (pcmStreaming) pipeline is the live command
  /// path -- i.e. not currently handed off to the free on-device recognizer
  /// because streaming/STT failed.
  bool get _pcmLive => !_pcmFallbackActive;
  late final MicrophoneService _pcmMicrophone = MicrophoneService(
    config: const AudioPipelineConfig(
      sampleRate: AppConfig.streamingAudioSampleRate,
    ),
  );
  late final AudioStreamer _audioStreamer = AudioStreamer(
    _connection,
    config: const AudioPipelineConfig(
      sampleRate: AppConfig.streamingAudioSampleRate,
    ),
  );
  final AudioOutputService _audioOutput = AudioOutputService();
  final AudioPlayer _tonePlayer = AudioPlayer();
  final PermissionManager _permissions = PermissionManager();
  final Logger _logger = Logger();
  final List<StreamSubscription<dynamic>> _subscriptions = [];

  RobotDisplayState _robotState = RobotDisplayState.offline;
  String _expression = 'neutral';
  RobotMood _mood = const RobotMood();
  String _brainUrl = AppConfig.defaultBrainUrl;
  // Same host/port as the websocket connection, but as a plain http(s)
  // base -- used for the odd one-off REST call (e.g. the doodle
  // overlay's subject pick) that doesn't belong on the websocket
  // protocol. Derived, not separately configured, so it never drifts out
  // of sync with whatever server URL Settings points at.
  String get _httpBaseUrl => _brainUrl
      .replaceFirst('ws://', 'http://')
      .replaceFirst('wss://', 'https://')
      .replaceFirst(RegExp(r'/ws/device/?$'), '');
  bool _debugVisible = false;
  bool _connected = false;
  bool _speechDetected = false;
  double _microphoneLevel = 0;
  bool _cameraReady = false;
  bool _microphoneReady = false;
  String _lastTranscript = '';
  String _lastReply = 'Estou pronto para ouvir.';
  Timer? _speechCommitTimer;
  Timer? _legacyFallbackRetryTimer;
  String _pendingTranscript = '';
  String _lastSubmittedTranscript = '';
  DateTime? _lastSubmittedAt;
  Offset? _trackedFace;
  AudioFrameMetrics? _audioMetrics;
  AudioStreamMetrics _streamMetrics = const AudioStreamMetrics();
  final PreRollBuffer _preRoll = PreRollBuffer(
    const AudioPipelineConfig(sampleRate: AppConfig.streamingAudioSampleRate),
  );
  String _partialTranscript = '';
  String? _lastFallbackReason;
  bool _pcmFallbackActive = false;
  DateTime? _pcmSpeechStartedAt;
  DateTime? _pcmSpeechEndedAt;
  Duration? _partialLatency;
  Duration? _finalLatency;
  bool _idleOverlayVisible = false;
  // Which self-entertainment vignette is currently showing. Picked
  // randomly each time an idle animation is triggered (see
  // _triggerIdleAnimation); null only before the first one ever runs.
  String? _idleActivityKind;
  static const _idleActivityKinds = [
    'snake', 'checkers', 'chess', 'reading',
    'resting', 'bored', 'coffee', 'humming', 'doodle',
  ];
  // Rough expected duration (seconds) of each activity -- picking evenly
  // at random would let a long game (checkers/chess, up to 2.5min) hog
  // just as much total on-screen time as a 20s snake doodle, which reads
  // as the games "dominating". Picks are weighted inversely by duration
  // instead, so every activity gets roughly the same total screen time
  // over a long stretch, not the same pick count. See _pickIdleActivity.
  static const _idleActivityDurationSeconds = {
    'snake': 20.0,
    'reading': 30.0,
    'checkers': 150.0,
    'chess': 150.0,
    'resting': 26.0,
    'bored': 22.0,
    'coffee': 25.0,
    'humming': 22.0,
    'doodle': 28.0,
  };
  // How restful each activity reads (0 = pretty active, 1 = pretty
  // parked) -- used to bias picks by mood (see _pickIdleActivity): tired
  // pulls toward the high end of this scale, curious/awake pulls toward
  // the low end.
  static const _idleActivityRestfulness = {
    'resting': 1.0,
    'coffee': 0.8,
    'reading': 0.75,
    'bored': 0.6,
    'doodle': 0.4,
    'humming': 0.35,
    'snake': 0.15,
    'checkers': 0.1,
    'chess': 0.1,
  };
  final _idleActivityRandom = math.Random();
  // The food currently being "eaten" (see IdleFeedOverlay) after a
  // feed_animation message -- null when nothing's being fed right now.
  // Independent of the idle-vignette system: can show up on top of
  // anything else, and doesn't affect _idleOverlayVisible.
  String? _feedFood;
  int _feedKey = 0;
  // Driven by IdleFeedOverlay's onMouthOpen while it's showing -- see
  // RobotFaceWidget.mouthOpen.
  double _mouthOpen = 0;
  // True while ambient playback is happening elsewhere (someone's phone,
  // PC...) and Bob isn't presenting his own player -- puts headphones on
  // his face, "listening along". Set from `set_ambient_listening`
  // messages (api/server.py's music sync loop); persistent, not an idle
  // vignette, so it can be true regardless of what else is on screen.
  bool _ambientListening = false;
  static const _feedGaze = Offset(0.5, 0.82);
  PresentationScene? _activeScene;
  Timer? _sceneTimer;
  static const _idleOverlayGaze = Offset(0.15, 0.15);
  // Looking down-center, toward each of these vignette's own bottom-center
  // staged prop (the book, the coffee mug, the sketch pad) -- distinct
  // from _idleOverlayGaze (top-left, where the two board games sit).
  static const _readingGaze = Offset(0.5, 0.86);
  static const _coffeeGaze = Offset(0.5, 0.82);
  static const _doodleGaze = Offset(0.5, 0.84);
  // A relaxed, unfocused middle distance -- not fixated on anything in
  // particular, matching "resting"/"bored".
  static const _restingGaze = Offset(0.5, 0.55);
  static const _boredGaze = Offset(0.5, 0.45);

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
        unawaited(_pauseAudioInput());
      },
      onCompleted: () {
        unawaited(_resumeAudioInput());
      },
      onCancelled: () {
        unawaited(_resumeAudioInput());
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
    _subscriptions.add(_connection.onBinaryMessage.listen(_handleBinaryFrame));
    _subscriptions.add(_connection.onStatus.listen((status) {
      if (!mounted) return;
      final connected = status == ConnectionStatus.connected;
      if (connected) unawaited(_reportDeviceState());
      setState(() {
        _connected = connected;
        if (!connected) _robotState = RobotDisplayState.offline;
      });
      if (!connected && _pcmLive) {
        _audioStreamer.cancel('connection_lost');
      }
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
      // Not used to dismiss the idle overlay: this reflects the recognizer
      // session being open, not actual voice activity, and flickers on
      // ambient noise -- it would kill the animation almost immediately.
      setState(() => _speechDetected = listening);
    }));
    _subscriptions.add(_speechRecognition.results.listen((result) {
      if (_pcmLive) return; // pcmStreaming is the live command path here
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
    _subscriptions.add(_pcmMicrophone.levelStream.listen((level) {
      if (!mounted || !_pcmLive) return;
      setState(() => _microphoneLevel = level);
    }));
    _subscriptions.add(_pcmMicrophone.metrics.listen((metrics) {
      if (!mounted) return;
      setState(() => _audioMetrics = metrics);
    }));
    _subscriptions.add(_pcmMicrophone.audioStream.listen((chunk) {
      if (!_pcmLive) return;
      if (_audioStreamer.streamId == null) {
        _preRoll.add(chunk);
      } else {
        _audioStreamer.enqueue(chunk);
      }
    }));
    _subscriptions.add(_pcmMicrophone.speechEvents.listen((event) {
      if (!_pcmLive) return;
      if (event == SpeechEvent.started) {
        // Not dismissing the idle overlay here on purpose -- this is raw
        // local voice-activity detection, which fires on any ambient
        // speech/noise, not specifically on someone calling the robot.
        // The overlay is dismissed once the backend actually confirms the
        // wake word (see the 'wake_state' handler above).
        _pcmSpeechStartedAt = DateTime.now();
        _audioStreamer.start();
        for (final frame in _preRoll.drain()) {
          _audioStreamer.enqueue(frame);
        }
        if (mounted) setState(() => _speechDetected = true);
      } else {
        _pcmSpeechEndedAt = DateTime.now();
        _audioStreamer.finish();
        if (mounted) {
          setState(() => _speechDetected = false);
          _setRobotState(RobotDisplayState.thinking);
        }
      }
    }));
    _subscriptions.add(_audioStreamer.metrics.listen((metrics) {
      if (mounted) setState(() => _streamMetrics = metrics);
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
    _dismissIdleOverlay();
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
      _logger.e('Camera initialization failed',
          error: error, stackTrace: stackTrace);
    }
  }

  /// Streaming (pcmStreaming) always runs -- it's the reliable pipeline.
  /// The wake word is spotted server-side against its transcripts instead
  /// of via a separate free/local listener (see AudioStreamCoordinator in
  /// api/server.py); the on-device recognizer here is kept only as the
  /// emergency fallback for when streaming/STT itself fails.
  Future<void> _startMicrophone() async {
    try {
      await _pcmMicrophone.start();
      if (mounted) setState(() => _microphoneReady = true);
    } catch (error, stackTrace) {
      _logger.e('Microphone initialization failed',
          error: error, stackTrace: stackTrace);
    }
  }

  // Magic prefix for a Piper-synthesized WAV clip (mirrors the RBA1 magic
  // AudioStreamer.frameAudio uses in the other direction, for mic audio).
  static const _ttsAudioMagic = [0x52, 0x42, 0x54, 0x31]; // "RBT1"

  void _handleBinaryFrame(Uint8List data) {
    if (data.length <= 4) return;
    for (var i = 0; i < 4; i++) {
      if (data[i] != _ttsAudioMagic[i]) return;
    }
    unawaited(_audioOutput.playBytes(data.sublist(4)));
  }

  void _handleIncomingMessage(Map<String, dynamic> json) {
    final message = RobotMessage.fromJson(json);
    switch (message.type) {
      case 'transcript_partial':
        final text = '${message.payload?['text'] ?? ''}'.trim();
        if (text.isNotEmpty && mounted) {
          _partialLatency ??= _pcmSpeechStartedAt == null
              ? null
              : DateTime.now().difference(_pcmSpeechStartedAt!);
          setState(() {
            _partialTranscript = text;
            _lastTranscript = text;
          });
        }
        return;
      case 'transcript_final':
        final text = '${message.payload?['text'] ?? ''}'.trim();
        if (_pcmSpeechEndedAt != null) {
          _finalLatency = DateTime.now().difference(_pcmSpeechEndedAt!);
        }
        if (text.isNotEmpty && mounted) {
          setState(() {
            _partialTranscript = '';
            _lastTranscript = text;
          });
        } else if (mounted) {
          _setRobotState(RobotDisplayState.idle);
        }
        return;
      case 'audio_stream_closed':
        if (mounted && _robotState == RobotDisplayState.thinking) {
          _setRobotState(RobotDisplayState.idle);
        }
        return;
      case 'audio_stream_error':
        // The backend also sends this for routine, expected stream
        // teardown (a new utterance superseding the previous one, the mic
        // pausing while the robot talks, the socket going away) -- only a
        // genuine STT-provider failure sets fallback_recommended, and only
        // that should give up on this pipeline for the on-device
        // recognizer. Falling back on every routine cancel would silently
        // and permanently break the wake-word gate (the legacy path never
        // goes through it) the first time the robot ever spoke.
        if (message.payload?['fallback_recommended'] == true) {
          final reason = '${message.payload?['code'] ?? 'STT_ERROR'}';
          unawaited(_activateLegacyFallback(reason));
        }
        return;
      case 'set_state':
        _setRobotState(
            _parseDisplayState('${message.payload?['state'] ?? 'IDLE'}'));
        return;
      case 'set_expression':
      case 'expression':
        final value = message.payload?['expression'] ??
            message.payload?['value'] ??
            json['value'] ??
            'neutral';
        final payload = message.payload;
        if (mounted) {
          setState(() {
            _expression = value.toString().toLowerCase();
            if (payload != null) {
              _mood = RobotMood.fromPayload(payload, previous: _mood);
            }
          });
        }
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
      case 'show_scene':
        final payload = message.payload;
        if (payload != null) _showScene(PresentationScene.fromPayload(payload));
        return;
      case 'dismiss_scene':
        _dismissScene();
        return;
      case 'device_control':
        final payload = message.payload;
        if (payload != null) unawaited(_applyDeviceControl(payload));
        return;
      case 'play_idle_animation':
        _triggerIdleAnimation(kind: message.payload?['kind'] as String?);
        return;
      case 'feed_animation':
        _triggerFeedAnimation(message.payload?['food'] as String? ?? '🍎');
        return;
      case 'set_ambient_listening':
        final listening = message.payload?['listening'] == true;
        if (mounted) setState(() => _ambientListening = listening);
        return;
      case 'wake_state':
        final awake = message.payload?['awake'] == true;
        _logger.i(
            'wake_state received: awake=$awake pcmMicRunning=${_pcmMicrophone.isRunning} pcmFallbackActive=$_pcmFallbackActive');
        if (mounted) {
          setState(
              () => _wakeState = awake ? WakeState.active : WakeState.standby);
        }
        // Only a confirmed wake word (the backend telling us so, here --
        // not just local mic/VAD activity, which fires on any ambient
        // noise or unrelated speech) should interrupt an idle vignette.
        if (awake) _dismissIdleOverlay();
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

  Future<void> _pauseAudioInput() async {
    _logger
        .i('mic paused for playback: wakeState=$_wakeState pcmLive=$_pcmLive');
    if (_pcmLive) {
      _audioStreamer.cancel('playback_started');
      // Tried muting instead of stopping here to skip the OS's audio-route
      // renegotiation cost on every robot utterance, but the recording
      // session itself goes dead once playback claims the audio focus --
      // muting our own processing doesn't bring it back, and unmuting
      // afterward produced zero further audio at all (confirmed live: no
      // command was ever captured across an entire wake window). Back to a
      // real stop/restart, which is slower but actually works.
      await _pcmMicrophone.stop();
    } else {
      await _speechRecognition.stop();
    }
  }

  Future<void> _resumeAudioInput() async {
    // Marks the gap between "done talking" and "mic is actually capturing
    // again" with a visibly different eye look (reusing the existing
    // "thinking" pose) so it's never mistaken for "listening" -- the mic
    // genuinely isn't ready yet during this window (the OS needs a moment
    // to re-acquire the recording route on this hardware; see the comment
    // below), so pretending otherwise would just teach the user to talk
    // into a mic that isn't there yet.
    _setRobotState(RobotDisplayState.thinking);
    if (_pcmLive) {
      // No artificial delay here -- restart immediately and let echoCancel
      // handle any tail-end overlap. The remaining latency users notice
      // (observed live to be roughly 1-2s) is the OS itself re-acquiring
      // the mic route on this device, not anything we're choosing to wait
      // for; there's no further software-level reduction available short
      // of native platform code.
      _pcmMicrophone.resetForListening();
      await _pcmMicrophone.start();
    } else {
      // The legacy on-device recognizer was observed to need real settling
      // time here; leave its delay alone.
      await Future<void>.delayed(const Duration(milliseconds: 450));
      await _speechRecognition.start();
    }
    // The mic is genuinely capturing again now -- safe to show as idle
    // (or whatever state a subsequent server message sets it to).
    _setRobotState(RobotDisplayState.idle);
    _logger.i(
        'mic resumed after playback: wakeState=$_wakeState pcmLive=$_pcmLive');
    // Tell the brain the mic is actually listening again, so it can arm its
    // wake-inactivity timer (or move on from a turn) against this real
    // signal instead of a server-side guess at how long playback+resume
    // would take.
    final sent = _connection.sendMessage(
      RobotMessageFactory.speechPlaybackDone(deviceId: AppConfig.deviceId),
    );
    _logger.i(
        'speech_playback_done sent=$sent connected=${_connection.isConnected}');
  }

  Future<void> _activateLegacyFallback(String reason) async {
    if (_pcmFallbackActive) return;
    _pcmFallbackActive = true;
    _lastFallbackReason = reason;
    _audioStreamer.cancel(reason);
    await _pcmMicrophone.stop();
    final available =
        _speechRecognition.isAvailable || await _speechRecognition.initialize();
    if (available) await _speechRecognition.start();
    if (mounted) setState(() => _microphoneReady = available);
    // A single transient STT/network hiccup shouldn't cost the wake-word
    // feature (which only the streaming pipeline goes through) for the
    // rest of the session -- try switching back after a while rather than
    // staying on the legacy recognizer until the app is restarted.
    _legacyFallbackRetryTimer?.cancel();
    _legacyFallbackRetryTimer =
        Timer(AppConfig.legacyFallbackRetryDelay, _retryStreamingPipeline);
  }

  Future<void> _retryStreamingPipeline() async {
    if (!_pcmFallbackActive) return;
    _logger.i(
        'retrying pcmStreaming pipeline after fallback: reason=$_lastFallbackReason');
    await _speechRecognition.stop();
    _pcmFallbackActive = false;
    _pcmMicrophone.resetForListening();
    await _pcmMicrophone.start();
    // If this attempt also fails, the next audio_stream_error with
    // fallback_recommended:true routes straight back through
    // _activateLegacyFallback (its own guard resets cleanly since
    // _pcmFallbackActive is false again), re-arming this same retry timer.
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
    final newUrl = await _navigatorKey.currentState?.push<String>(
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

  /// The brain only ever decides *when* the robot entertains itself; *what*
  /// it does is picked locally so the protocol stays a single bare message
  /// and new idle activities can be added here without touching the
  /// backend. [kind] is an optional debug-only override (one of
  /// _idleActivityKinds) sent by /debug/idle_animation to force a specific
  /// one during manual testing -- production ticks never set it, so the
  /// pick stays random as designed.
  void _triggerIdleAnimation({String? kind}) {
    if (!mounted || _idleOverlayVisible) return;
    setState(() {
      _idleOverlayVisible = true;
      _idleActivityKind = _idleActivityKinds.contains(kind)
          ? kind
          : _pickIdleActivity();
    });
    _reportIdleActivity(_idleActivityKind);
  }

  /// Applies a `device_control` from the backend (Bob adjusting the
  /// tablet's own volume/brightness) and reports the resulting state.
  Future<void> _applyDeviceControl(Map<String, dynamic> payload) async {
    final state = await DeviceControls.apply(payload);
    if (state != null) await _reportDeviceState(state);
  }

  Future<void> _reportDeviceState([Map<String, int>? known]) async {
    final state = known ?? await DeviceControls.getState();
    if (state == null) return;
    _connection.sendMessage(
      RobotMessageFactory.deviceState(
        deviceId: AppConfig.deviceId,
        volume: state['volume'] ?? 0,
        brightness: state['brightness'] ?? 0,
      ),
    );
  }

  void _dismissIdleOverlay() {
    if (_idleOverlayVisible && mounted) {
      setState(() => _idleOverlayVisible = false);
      _reportIdleActivity(null);
    }
  }

  /// Tells the backend which idle vignette (if any) is showing right
  /// now, so its cognition tick can actually respond to it (see
  /// RobotMessageFactory.idleActivityReport) instead of it being purely
  /// cosmetic.
  void _reportIdleActivity(String? kind) {
    _connection.sendMessage(
      RobotMessageFactory.idleActivityReport(
        deviceId: AppConfig.deviceId,
        kind: kind,
      ),
    );
  }

  void _triggerFeedAnimation(String food) {
    if (!mounted) return;
    setState(() {
      _feedFood = food;
      _feedKey++;
    });
  }

  /// Called when a vignette ends on its own (a simulated "win/loss", or
  /// its own internal timer) rather than from a real interruption --
  /// swaps in a different activity right away instead of leaving the
  /// face blank, so it still reads as the robot doing something.
  void _idleActivityFinished() {
    if (!mounted || !_idleOverlayVisible) return;
    setState(() {
      _idleActivityKind = _pickIdleActivity(exclude: _idleActivityKind);
    });
    _reportIdleActivity(_idleActivityKind);
  }

  /// Weighted pick across [_idleActivityKinds]. The base weight is
  /// inversely proportional to how long an activity typically runs
  /// (_idleActivityDurationSeconds), so short and long activities end up
  /// getting roughly the same total screen time instead of the same pick
  /// count -- then scaled by [_moodFactor] so how tired/awake Bob
  /// actually is nudges what he picks (tired leans restful, curious
  /// leans active) instead of picking blind to his own state.
  /// [exclude], when given, is left out so a chained pick (after one
  /// vignette just finished) doesn't immediately repeat itself.
  String _pickIdleActivity({String? exclude}) {
    var candidates = _idleActivityKinds
        .where((k) => k != exclude && _isEligible(k))
        .toList();
    // If gating leaves nothing (a real edge case: e.g. excluding the
    // just-finished kind also happened to remove the only eligible one),
    // fall back to every kind rather than crashing on an empty pool.
    if (candidates.isEmpty) {
      candidates = _idleActivityKinds.where((k) => k != exclude).toList();
    }
    final pool = candidates.isNotEmpty ? candidates : _idleActivityKinds;
    final weights = [
      for (final k in pool) (1 / _idleActivityDurationSeconds[k]!) * _moodFactor(k)
    ];
    final total = weights.reduce((a, b) => a + b);
    var roll = _idleActivityRandom.nextDouble() * total;
    for (var i = 0; i < pool.length; i++) {
      roll -= weights[i];
      if (roll <= 0) return pool[i];
    }
    return pool.last;
  }

  /// How much [kind] fits Bob's current mood, as a multiplier on its
  /// base weight in [_pickIdleActivity]. Combines two signals already
  /// live in `_mood` (fed continuously by `set_expression`): the more
  /// tired he is, the more the pick leans toward restful activities
  /// (weighted by each kind's own [_idleActivityRestfulness]); the more
  /// curious/awake he is, the more it leans toward active ones.
  /// A hard gate, not just a weight nudge: "resting"/"coffee" shouldn't
  /// even be in the running unless Bob is actually somewhat tired, and
  /// "bored" shouldn't be in the running unless he's actually been idle
  /// a while -- picking them regardless (just less often) read as
  /// arbitrary rather than attribute-driven. Everything else stays
  /// always-eligible, weighted by mood as before.
  bool _isEligible(String kind) {
    final tiredness = 1 - _mood.energy;
    switch (kind) {
      case 'resting':
      case 'coffee':
        return tiredness > 0.3;
      case 'bored':
        return _mood.boredom > 0.15;
      default:
        return true;
    }
  }

  double _moodFactor(String kind) {
    final restfulness = _idleActivityRestfulness[kind]!;
    final tiredness = 1 - _mood.energy;
    return 1 +
        tiredness * restfulness * 2.2 +
        _mood.curiosity * (1 - restfulness) * 1.3;
  }

  /// How long a restful activity (reading/resting/bored/coffee) should
  /// actually run for, given [kind] and how tired Bob currently is.
  /// These four are all short by design (~20-30s each, so no single one
  /// hogs screen time -- see _idleActivityDurationSeconds), but that
  /// also means being tired biases toward the whole short-restful
  /// cluster at once, which without this would just look like rapid,
  /// restless cycling between four different "calm" vignettes instead
  /// of him actually settling down for a stretch. Stretches the base
  /// duration up to ~3x at full tiredness; unaffected when well-rested.
  Duration _restfulDuration(String kind) {
    final base = _idleActivityDurationSeconds[kind]!;
    final tiredness = 1 - _mood.energy;
    return Duration(seconds: (base * (1 + tiredness * 2)).round());
  }

  void _showScene(PresentationScene scene) {
    if (!mounted) return;
    _sceneTimer?.cancel();
    _dismissIdleOverlay();
    setState(() => _activeScene = scene);
    if (!scene.persistent && scene.duration != null) {
      _sceneTimer = Timer(scene.duration!, _dismissScene);
    }
  }

  void _dismissScene() {
    _sceneTimer?.cancel();
    _sceneTimer = null;
    if (mounted && _activeScene != null) setState(() => _activeScene = null);
  }

  RobotDisplayState _parseDisplayState(String value) {
    return RobotDisplayState.values.firstWhere(
      (state) => state.label == value.trim().toUpperCase(),
      orElse: () => RobotDisplayState.idle,
    );
  }

  // `Navigator.of(context)` needs a context *below* the Navigator this
  // MaterialApp creates -- the State's own `context` (used previously) sits
  // above it, since this build() method is what constructs the MaterialApp.
  // A dedicated key lets `_openSettings` reach the Navigator directly.
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: Colors.black,
      ),
      home: Scaffold(
        body: SafeArea(
          child: Stack(
            children: [
              Positioned.fill(
                child: GestureDetector(
                  onLongPress: () =>
                      setState(() => _debugVisible = !_debugVisible),
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 420),
                    switchInCurve: Curves.easeOut,
                    switchOutCurve: Curves.easeIn,
                    child: _activeScene == null
                        ? RobotFaceWidget(
                            key: const ValueKey('robot-face'),
                            expression: _expression,
                            mood: _mood,
                            state: _robotState,
                            microphoneLevel: _microphoneLevel,
                            speechDetected: _speechDetected,
                            trackedFace: _feedFood != null
                                ? _feedGaze
                                : _idleOverlayVisible
                                    ? (switch (_idleActivityKind) {
                                        'reading' => _readingGaze,
                                        'coffee' => _coffeeGaze,
                                        'doodle' => _doodleGaze,
                                        'resting' => _restingGaze,
                                        'bored' => _boredGaze,
                                        _ => _idleOverlayGaze,
                                      })
                                    : _trackedFace,
                            isPlaying:
                                _idleOverlayVisible && _idleActivityKind == 'snake',
                            readingGlasses: _idleOverlayVisible &&
                                _idleActivityKind == 'reading',
                            restingEyes: _idleOverlayVisible &&
                                _idleActivityKind == 'resting',
                            headphones: _ambientListening ||
                                (_idleOverlayVisible &&
                                    _idleActivityKind == 'humming'),
                            mouthOpen: _mouthOpen,
                            hueOverride:
                                _wakeState == WakeState.standby ? 205.0 : 135.0,
                          )
                        : PresentationSceneWidget(
                            key: ValueKey(
                                '${_activeScene!.kind}:${_activeScene!.variant}'),
                            scene: _activeScene!,
                          ),
                  ),
                ),
              ),
              if (_idleOverlayVisible && _activeScene == null)
                Positioned.fill(
                  child: switch (_idleActivityKind) {
                    'checkers' => IdleCheckersOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        httpBaseUrl: _httpBaseUrl),
                    'chess' => IdleChessOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        httpBaseUrl: _httpBaseUrl),
                    'reading' => IdleReadingOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        maxDuration: _restfulDuration('reading'),
                        httpBaseUrl: _httpBaseUrl),
                    'resting' => IdleRestingOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        maxDuration: _restfulDuration('resting')),
                    'bored' => IdleBoredOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        maxDuration: _restfulDuration('bored')),
                    'coffee' => IdleCoffeeOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        maxDuration: _restfulDuration('coffee')),
                    'humming' => IdleHummingOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished),
                    'doodle' => IdleDoodleOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished,
                        httpBaseUrl: _httpBaseUrl),
                    _ => IdleSnakeOverlay(
                        key: ValueKey(_idleActivityKind),
                        mood: _mood,
                        onDismiss: _dismissIdleOverlay,
                        onFinished: _idleActivityFinished),
                  },
                ),
              if (_feedFood != null)
                Positioned.fill(
                  child: IdleFeedOverlay(
                    key: ValueKey('feed-$_feedKey'),
                    food: _feedFood!,
                    onDone: () {
                      if (mounted) setState(() => _feedFood = null);
                    },
                    onMouthOpen: (v) {
                      if (mounted) setState(() => _mouthOpen = v);
                    },
                  ),
                ),
              // Always-reachable settings entry point -- the gear button
              // inside the debug panel below is easy to miss/mistap once the
              // panel is full of metric rows, and requires opening the panel
              // first. This one is a single tap away from any screen.
              Positioned(
                top: 8,
                right: 8,
                child: IconButton(
                  tooltip: 'Configurar conexão',
                  onPressed: () => unawaited(_openSettings()),
                  icon: const Icon(Icons.settings, color: Colors.white70),
                ),
              ),
              if (_activeScene == null) ...[
                Positioned(
                  left: 16,
                  bottom: 16,
                  child: _StatusPill(connected: _connected),
                ),
                Positioned(
                  top: 52,
                  right: 8,
                  child: AttributesPanel(mood: _mood),
                ),
              ],
              if (_activeScene == null || _debugVisible)
                Positioned(
                  right: 12,
                  bottom: 8,
                  child: IconButton(
                    tooltip: 'Diagnóstico',
                    onPressed: () =>
                        setState(() => _debugVisible = !_debugVisible),
                    icon: const Icon(Icons.bug_report_outlined),
                  ),
                ),
              if (_debugVisible)
                Align(
                  alignment: Alignment.topRight,
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    // The panel's own content can be taller than the screen
                    // (many metric rows) -- without a bounded height + scroll
                    // view here, it silently overflows and the bottom row
                    // (which holds the settings button) becomes unreachable.
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        maxHeight: MediaQuery.of(context).size.height - 32,
                      ),
                      child: SingleChildScrollView(
                        child: DebugPanel(
                          connected: _connected,
                          robotState: _robotState,
                          expression: _expression,
                          mood: _mood,
                          speechDetected: _speechDetected,
                          microphoneLevel: _microphoneLevel,
                          cameraReady: _cameraReady,
                          microphoneReady: _microphoneReady,
                          brainUrl: _brainUrl,
                          wakeState: _wakeState,
                          audioInputMode: _pcmFallbackActive
                              ? 'ANDROID (FALLBACK)'
                              : 'PCM_STREAMING',
                          audioMetrics: _audioMetrics,
                          streamMetrics: _streamMetrics,
                          partialTranscript: _partialTranscript,
                          lastFallbackReason: _lastFallbackReason,
                          partialLatency: _partialLatency,
                          finalLatency: _finalLatency,
                          onCaptureFrame: () =>
                              unawaited(_captureAndSendFrame()),
                          onOpenSettings: () => unawaited(_openSettings()),
                        ),
                      ),
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
    _legacyFallbackRetryTimer?.cancel();
    _sceneTimer?.cancel();
    for (final subscription in _subscriptions) {
      unawaited(subscription.cancel());
    }
    unawaited(_connection.dispose());
    unawaited(_speechRecognition.dispose());
    unawaited(_pcmMicrophone.dispose());
    unawaited(_audioStreamer.dispose());
    _camera.dispose();
    unawaited(_audioOutput.stop());
    unawaited(_tonePlayer.dispose());
    super.dispose();
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
