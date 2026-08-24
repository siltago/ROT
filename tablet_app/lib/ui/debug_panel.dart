import 'package:flutter/material.dart';

import '../robot/robot_display_state.dart';

class DebugPanel extends StatelessWidget {
  const DebugPanel({
    super.key,
    required this.connected,
    required this.robotState,
    required this.expression,
    required this.speechDetected,
    required this.microphoneLevel,
    required this.cameraReady,
    required this.microphoneReady,
    required this.brainUrl,
    required this.onCaptureFrame,
    required this.onOpenSettings,
  });

  final bool connected;
  final RobotDisplayState robotState;
  final String expression;
  final bool speechDetected;
  final double microphoneLevel;
  final bool cameraReady;
  final bool microphoneReady;
  final String brainUrl;
  final VoidCallback onCaptureFrame;
  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 300,
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
          _row('Expression', expression),
          _row('Volume', microphoneLevel.toStringAsFixed(2)),
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
          Text(value, style: const TextStyle(color: Colors.white)),
        ],
      ),
    );
  }
}
