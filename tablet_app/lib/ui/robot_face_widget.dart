import 'package:flutter/material.dart';

import '../robot/robot_display_state.dart';

class RobotFaceWidget extends StatelessWidget {
  const RobotFaceWidget({
    super.key,
    required this.expression,
    required this.state,
    required this.microphoneLevel,
    required this.speechDetected,
    required this.cameraPreview,
  });

  final String expression;
  final RobotDisplayState state;
  final double microphoneLevel;
  final bool speechDetected;
  final Widget cameraPreview;

  @override
  Widget build(BuildContext context) {
    final eyeScale = switch (state) {
      RobotDisplayState.listening => 1.2,
      RobotDisplayState.thinking => 1.0,
      RobotDisplayState.speaking => 1.5,
      RobotDisplayState.error => 0.8,
      _ => 1.0,
    };

    final innerEyeSize = 18.0 * eyeScale;
    final blink = state == RobotDisplayState.sleeping ? 0.2 : 1.0;

    return Container(
      width: 320,
      height: 420,
      decoration: BoxDecoration(
        color: const Color(0xFF111827),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: Colors.white24),
      ),
      child: Stack(
        children: [
          Positioned.fill(child: cameraPreview),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.15),
                borderRadius: BorderRadius.circular(28),
              ),
            ),
          ),
          Positioned(
            top: 16,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                state.label,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ),
          ),
          Center(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                AnimatedContainer(
                  duration: const Duration(milliseconds: 220),
                  width: innerEyeSize,
                  height: innerEyeSize * blink,
                  decoration: BoxDecoration(
                    color: speechDetected ? Colors.greenAccent : Colors.white,
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                const SizedBox(width: 56),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 220),
                  width: innerEyeSize,
                  height: innerEyeSize * blink,
                  decoration: BoxDecoration(
                    color: speechDetected ? Colors.greenAccent : Colors.white,
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            bottom: 18,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                width: 180,
                height: 10,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(100),
                  color: Colors.white24,
                ),
                child: FractionallySizedBox(
                  widthFactor: microphoneLevel.clamp(0.0, 1.0),
                  alignment: Alignment.centerLeft,
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(100),
                      color: speechDetected ? Colors.greenAccent : Colors.cyanAccent,
                    ),
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            bottom: 32,
            left: 0,
            right: 0,
            child: Center(
              child: Text(
                expression,
                style: const TextStyle(
                  color: Colors.white70,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
