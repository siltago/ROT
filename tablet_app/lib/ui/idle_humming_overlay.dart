import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A "humming along to something" vignette -- headphones on (drawn on
/// the face itself, see [RobotFaceWidget.headphones]) with a small
/// equalizer bounce held low and centered, like the robot's idly
/// listening to a tune only it can hear. No card/label chrome. No
/// "losing" condition; ends after [maxDuration] (or [onDismiss] on
/// interruption).
class IdleHummingOverlay extends StatefulWidget {
  const IdleHummingOverlay({
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
  State<IdleHummingOverlay> createState() => _IdleHummingOverlayState();
}

class _IdleHummingOverlayState extends State<IdleHummingOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _beat;
  final _random = math.Random();
  late List<double> _barSeeds;
  Timer? _dismissTimer;

  @override
  void initState() {
    super.initState();
    _barSeeds = List.generate(5, (_) => _random.nextDouble() * 2 * math.pi);
    _beat = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    _beat.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color =
        HSLColor.fromAHSL(1, 190 + widget.mood.curiosity * 60, 0.65, 0.68)
            .toColor();
    const width = 110.0;
    return IgnorePointer(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 88),
          child: SizedBox(
            width: width,
            height: 44,
            child: AnimatedBuilder(
              animation: _beat,
              builder: (context, _) => CustomPaint(
                painter: _EqualizerPainter(color: color, t: _beat.value, seeds: _barSeeds),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _EqualizerPainter extends CustomPainter {
  _EqualizerPainter({required this.color, required this.t, required this.seeds});

  final Color color;
  final double t;
  final List<double> seeds;

  @override
  void paint(Canvas canvas, Size size) {
    final barCount = seeds.length;
    final barWidth = size.width / (barCount * 2 - 1);
    for (var i = 0; i < barCount; i++) {
      final phase = t * 2 * math.pi * (1 + i * 0.15) + seeds[i];
      final level = 0.25 + 0.7 * (0.5 + 0.5 * math.sin(phase));
      final barHeight = size.height * level;
      final x = i * barWidth * 2;
      final rect = Rect.fromLTWH(x, size.height - barHeight, barWidth, barHeight);
      canvas.drawRRect(
        RRect.fromRectAndRadius(rect, Radius.circular(barWidth * 0.4)),
        Paint()..color = color.withValues(alpha: 0.55 + 0.3 * level),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _EqualizerPainter oldDelegate) => oldDelegate.t != t;
}
