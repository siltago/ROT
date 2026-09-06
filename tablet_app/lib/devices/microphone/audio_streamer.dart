import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

import '../../app/config.dart';
import '../../core/connection/robot_connection.dart';
import '../../core/protocol/protocol.dart';
import 'audio_pipeline.dart';

enum AudioInputMode {
  androidSpeechRecognizer,
  pcmStreaming;

  static AudioInputMode parse(String value) => value == 'pcmStreaming'
      ? AudioInputMode.pcmStreaming
      : AudioInputMode.androidSpeechRecognizer;
}

class FinalTranscript {
  const FinalTranscript({
    required this.text,
    required this.startedAt,
    required this.endedAt,
    required this.source,
    this.confidence,
  });
  final String text;
  final double? confidence;
  final DateTime startedAt;
  final DateTime endedAt;
  final String source;
}

class AudioStreamMetrics {
  const AudioStreamMetrics({
    this.streamId,
    this.sequence = 0,
    this.queuedChunks = 0,
    this.sentChunks = 0,
    this.droppedChunks = 0,
  });
  final String? streamId;
  final int sequence;
  final int queuedChunks;
  final int sentChunks;
  final int droppedChunks;
}

class AudioStreamer {
  AudioStreamer(
    this.connection, {
    this.config = const AudioPipelineConfig(sampleRate: 24000),
  });

  final RobotConnection connection;
  final AudioPipelineConfig config;
  final Queue<Uint8List> _queue = Queue<Uint8List>();
  final StreamController<AudioStreamMetrics> _metrics =
      StreamController<AudioStreamMetrics>.broadcast();
  String? _streamId;
  int _sequence = 0;
  int _sent = 0;
  int _dropped = 0;
  bool _flushScheduled = false;

  Stream<AudioStreamMetrics> get metrics => _metrics.stream;
  String? get streamId => _streamId;

  String start() {
    if (_streamId != null) cancel('replaced_by_new_stream');
    _streamId =
        'audio_${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}';
    _sequence = 0;
    _sent = 0;
    _dropped = 0;
    connection.sendMessage(
      RobotMessageFactory.audioStreamStart(
        deviceId: AppConfig.deviceId,
        streamId: _streamId!,
        sampleRate: config.sampleRate,
        channels: config.channels,
        chunkMs: config.chunkMs,
      ),
    );
    connection.sendMessage(
      RobotMessageFactory.speechStarted(
        deviceId: AppConfig.deviceId,
        streamId: _streamId!,
      ),
    );
    _emitMetrics();
    return _streamId!;
  }

  void enqueue(Uint8List pcm) {
    if (_streamId == null) return;
    final frame = frameAudio(_sequence++, pcm);
    if (_queue.length >= config.maxQueuedChunks) {
      _queue.removeFirst();
      _dropped++;
    }
    _queue.add(frame);
    _scheduleFlush();
    _emitMetrics();
  }

  void finish() {
    final streamId = _streamId;
    if (streamId == null) return;
    _flush();
    connection.sendMessage(
      RobotMessageFactory.speechEnded(
        deviceId: AppConfig.deviceId,
        streamId: streamId,
      ),
    );
    connection.sendMessage(
      RobotMessageFactory.audioStreamEnd(
        deviceId: AppConfig.deviceId,
        streamId: streamId,
      ),
    );
    _streamId = null;
    _emitMetrics();
  }

  void cancel(String reason) {
    final streamId = _streamId;
    _queue.clear();
    _streamId = null;
    if (streamId != null) {
      connection.sendMessage(
        RobotMessageFactory.audioStreamCancel(
          deviceId: AppConfig.deviceId,
          streamId: streamId,
          reason: reason,
        ),
      );
    }
    _emitMetrics();
  }

  void _scheduleFlush() {
    if (_flushScheduled) return;
    _flushScheduled = true;
    scheduleMicrotask(_flush);
  }

  void _flush() {
    _flushScheduled = false;
    while (_queue.isNotEmpty && connection.isConnected) {
      if (!connection.sendBinary(_queue.removeFirst())) break;
      _sent++;
    }
    if (_queue.isNotEmpty && connection.isConnected) _scheduleFlush();
    _emitMetrics();
  }

  void _emitMetrics() {
    if (_metrics.isClosed) return;
    _metrics.add(AudioStreamMetrics(
      streamId: _streamId,
      sequence: _sequence,
      queuedChunks: _queue.length,
      sentChunks: _sent,
      droppedChunks: _dropped,
    ));
  }

  static Uint8List frameAudio(int sequence, Uint8List pcm) {
    final result = Uint8List(8 + pcm.length);
    result.setRange(0, 4, const [0x52, 0x42, 0x41, 0x31]);
    ByteData.sublistView(result).setUint32(4, sequence, Endian.big);
    result.setRange(8, result.length, pcm);
    return result;
  }

  Future<void> dispose() async {
    cancel('disposed');
    await _metrics.close();
  }
}
