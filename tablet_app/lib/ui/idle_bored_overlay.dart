import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A "nothing much going on" vignette -- a slow pulsing "..." floating
/// unobtrusively near the top, no card/label chrome, reading as mild
/// boredom rather than any specific activity. No "losing" condition;
/// ends after [maxDuration] (or [onDismiss] on interruption).
class IdleBoredOverlay extends StatefulWidget {
  const IdleBoredOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    this.maxDuration = const Duration(seconds: 22),
  });

  final RobotMood mood;
  final VoidCallback onDismiss;
  final VoidCallback onFinished;
  final Duration maxDuration;

  @override
  State<IdleBoredOverlay> createState() => _IdleBoredOverlayState();
}

class _IdleBoredOverlayState extends State<IdleBoredOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;
  Timer? _dismissTimer;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color =
        HSLColor.fromAHSL(1, 190 + widget.mood.curiosity * 60, 0.65, 0.68)
            .toColor();
    return IgnorePointer(
      child: Align(
        alignment: Alignment.topCenter,
        child: Padding(
          padding: const EdgeInsets.only(top: 36),
          child: SizedBox(
            width: 70,
            height: 20,
            child: AnimatedBuilder(
              animation: _pulse,
              builder: (context, _) => CustomPaint(
                painter: _DotsPainter(color: color, t: _pulse.value),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _DotsPainter extends CustomPainter {
  _DotsPainter({required this.color, required this.t});

  final Color color;
  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final centerY = size.height / 2;
    for (var i = 0; i < 3; i++) {
      final phase = (t - i * 0.18) % 1.0;
      final eased = 0.5 - 0.5 * math.cos(phase.clamp(0, 1) * 2 * math.pi);
      final x = size.width / 2 + (i - 1) * size.height * 1.3;
      final r = size.height * (0.14 + 0.1 * eased);
      canvas.drawCircle(Offset(x, centerY), r, Paint()..color = color.withValues(alpha: 0.3 + 0.4 * eased));
    }
  }

  @override
  bool shouldRepaint(covariant _DotsPainter oldDelegate) => oldDelegate.t != t;
}
