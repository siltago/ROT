import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_display_state.dart';

class RobotFaceWidget extends StatefulWidget {
  const RobotFaceWidget({
    super.key,
    required this.expression,
    required this.state,
    required this.microphoneLevel,
    required this.speechDetected,
    required this.cameraPreview,
    required this.trackedFace,
  });

  final String expression;
  final RobotDisplayState state;
  final double microphoneLevel;
  final bool speechDetected;
  final Widget cameraPreview;
  final Offset? trackedFace;

  @override
  State<RobotFaceWidget> createState() => _RobotFaceWidgetState();
}

class _RobotFaceWidgetState extends State<RobotFaceWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _animation;

  @override
  void initState() {
    super.initState();
    _animation = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat(reverse: true);
  }

  @override
  Widget build(BuildContext context) {
    final color = _accentColor;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 350),
      color: widget.state == RobotDisplayState.error
          ? const Color(0xFF260A11)
          : const Color(0xFF070B16),
      child: Stack(
        children: [
          Center(
            child: AnimatedBuilder(
              animation: _animation,
              builder: (context, _) {
                final pulse = _animation.value;
                final target = widget.trackedFace ?? const Offset(0.5, 0.5);
                return AnimatedContainer(
                  duration: const Duration(milliseconds: 420),
                  curve: Curves.easeOutCubic,
                  transform: Matrix4.translationValues(
                    (target.dx - 0.5) * 120,
                    (target.dy - 0.5) * 55,
                    0,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _Eye(
                          color: color,
                          height: _eyeHeight(pulse),
                          rotation: _eyeRotation(left: true),
                        ),
                        const SizedBox(width: 86),
                        _Eye(
                          color: color,
                          height: _eyeHeight(pulse),
                          rotation: _eyeRotation(left: false),
                        ),
                      ],
                    ),
                    const SizedBox(height: 54),
                    _Mouth(
                      color: color,
                      expression: widget.expression,
                      speakingAmount: widget.state == RobotDisplayState.speaking
                          ? 0.35 + pulse * 0.65
                          : 0,
                    ),
                    const SizedBox(height: 38),
                    Text(
                      widget.state.label,
                      style: TextStyle(
                        color: color.withValues(alpha: 0.85),
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 3,
                      ),
                    ),
                    ],
                  ),
                );
              },
            ),
          ),
          Positioned(
            top: 18,
            right: 18,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: SizedBox(width: 112, height: 84, child: widget.cameraPreview),
            ),
          ),
          Positioned(
            left: 24,
            right: 24,
            bottom: 58,
            child: LinearProgressIndicator(
              value: widget.microphoneLevel.clamp(0, 1),
              minHeight: 5,
              borderRadius: BorderRadius.circular(8),
              color: widget.speechDetected ? Colors.greenAccent : color,
              backgroundColor: Colors.white10,
            ),
          ),
        ],
      ),
    );
  }

  double _eyeHeight(double pulse) {
    if (widget.state == RobotDisplayState.sleeping) return 7;
    if (widget.expression == 'happy') return 18;
    if (widget.expression == 'sad') return 22;
    if (widget.expression == 'confused') return 24 + pulse * 7;
    if (widget.state == RobotDisplayState.thinking) return 31 + pulse * 7;
    if (widget.state == RobotDisplayState.listening) return 46;
    return 37;
  }

  double _eyeRotation({required bool left}) {
    if (widget.expression == 'confused') return left ? -0.18 : 0.18;
    if (widget.expression == 'curious') return left ? 0.1 : -0.1;
    if (widget.expression == 'sad') return left ? 0.16 : -0.16;
    return 0;
  }

  Color get _accentColor {
    if (widget.state == RobotDisplayState.error) return Colors.redAccent;
    if (widget.state == RobotDisplayState.offline) return Colors.blueGrey;
    if (widget.expression == 'happy') return Colors.amberAccent;
    if (widget.expression == 'curious') return Colors.purpleAccent;
    if (widget.expression == 'sad') return Colors.lightBlueAccent;
    if (widget.state == RobotDisplayState.listening) return Colors.greenAccent;
    if (widget.state == RobotDisplayState.thinking) return Colors.cyanAccent;
    return const Color(0xFF8DEBFF);
  }

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }
}

class _Eye extends StatelessWidget {
  const _Eye({required this.color, required this.height, required this.rotation});
  final Color color;
  final double height;
  final double rotation;

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: rotation,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        width: 58,
        height: height,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(30),
          boxShadow: [
            BoxShadow(color: color.withValues(alpha: 0.35), blurRadius: 24),
          ],
        ),
      ),
    );
  }
}

class _Mouth extends StatelessWidget {
  const _Mouth({
    required this.color,
    required this.expression,
    required this.speakingAmount,
  });
  final Color color;
  final String expression;
  final double speakingAmount;

  @override
  Widget build(BuildContext context) {
    final happy = expression == 'happy';
    final confused = expression == 'confused';
    return Transform.rotate(
      angle: confused ? -0.08 : 0,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        width: happy ? 86 : 66,
        height: math.max(7.0, speakingAmount * 35).toDouble(),
        decoration: BoxDecoration(
          color: speakingAmount > 0 ? color.withValues(alpha: 0.32) : color,
          border: Border.all(color: color, width: 4),
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(happy ? 4 : 24),
            bottom: Radius.circular(happy ? 35 : 24),
          ),
        ),
      ),
    );
  }
}
