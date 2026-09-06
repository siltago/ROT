import 'package:flutter/material.dart';

import '../robot/robot_display_state.dart';
import '../robot/robot_mood.dart';
import '../robot/wake_state.dart';
import '../devices/microphone/audio_pipeline.dart';
import '../devices/microphone/audio_streamer.dart';

class DebugPanel extends StatelessWidget {
  const DebugPanel({
    super.key,
    required this.connected,
    required this.robotState,
    required this.expression,
    required this.mood,
    required this.speechDetected,
    required this.microphoneLevel,
    required this.cameraReady,
    required this.microphoneReady,
    required this.brainUrl,
    required this.wakeState,
    required this.audioInputMode,
    required this.audioMetrics,
    required this.streamMetrics,
    required this.partialTranscript,
    required this.lastFallbackReason,
    required this.partialLatency,
    required this.finalLatency,
    required this.onCaptureFrame,
    required this.onOpenSettings,
  });

  final bool connected;
  final RobotDisplayState robotState;
  final String expression;
  final RobotMood mood;
  final bool speechDetected;
  final double microphoneLevel;
  final bool cameraReady;
  final bool microphoneReady;
  final String brainUrl;
  final WakeState wakeState;
  final String audioInputMode;
  final AudioFrameMetrics? audioMetrics;
  final AudioStreamMetrics streamMetrics;
  final String partialTranscript;
  final String? lastFallbackReason;
  final Duration? partialLatency;
  final Duration? finalLatency;
  final VoidCallback onCaptureFrame;
  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 370,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.black87,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'ROBOT TABLET DEBUG',
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 16,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 12),
          _row('Connection', connected ? 'ONLINE' : 'OFFLINE'),
          _row('Brain', brainUrl),
          _row('Camera', cameraReady ? 'ACTIVE' : 'OFF'),
          _row('Microphone', microphoneReady ? 'ACTIVE' : 'OFF'),
          _row('Speech detected', speechDetected ? 'true' : 'false'),
          _row('Robot state', robotState.label),
          _row('Wake state', wakeState.name.toUpperCase()),
          _row('Expression', expression),
          _row('Valence', mood.valence.toStringAsFixed(2)),
          _row('Energy', mood.energy.toStringAsFixed(2)),
          _row('Irritation', mood.irritation.toStringAsFixed(2)),
          _row('Curiosity', mood.curiosity.toStringAsFixed(2)),
          _row('Volume', microphoneLevel.toStringAsFixed(2)),
          _row('Audio mode', audioInputMode),
          _row('PCM', 's16le / 24k / mono / 50ms'),
          _row('Stream', streamMetrics.streamId ?? '-'),
          _row('Sequence', '${streamMetrics.sequence}'),
          _row('Queue / dropped',
              '${streamMetrics.queuedChunks} / ${streamMetrics.droppedChunks}'),
          _row('VAD', audioMetrics?.vadState.name ?? '-'),
          _row('Turn', audioMetrics?.turnState.name ?? '-'),
          _row('dBFS', audioMetrics?.dbfs.toStringAsFixed(1) ?? '-'),
          _row('Noise floor',
              audioMetrics?.noiseFloorDb.toStringAsFixed(1) ?? '-'),
          _row('Threshold',
              audioMetrics?.dynamicThresholdDb.toStringAsFixed(1) ?? '-'),
          _row('STT', 'openai_realtime'),
          _row('Partial', partialTranscript.isEmpty ? '-' : partialTranscript),
          _row('Partial latency', _duration(partialLatency)),
          _row('Final latency', _duration(finalLatency)),
          _row('Fallback', lastFallbackReason ?? 'available'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: onCaptureFrame,
                  icon: const Icon(Icons.camera_alt_outlined),
                  label: const Text('Enviar frame'),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'Configurar conexão',
                onPressed: onOpenSettings,
                icon: const Icon(Icons.settings),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white70)),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white),
            ),
          ),
        ],
      ),
    );
  }

  String _duration(Duration? value) =>
      value == null ? '-' : '${value.inMilliseconds} ms';
}
