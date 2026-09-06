import 'dart:math' as math;

import 'package:flutter/material.dart';

/// A small isometric joystick, drawn (not an image asset) and gently wiggled
/// in a circle -- shown under the eyes while the robot is "playing" its own
/// idle game, as a charming visual echo of the snake overlay.
class AnimatedJoystick extends StatefulWidget {
  const AnimatedJoystick({super.key, this.size = 64});

  final double size;

  @override
  State<AnimatedJoystick> createState() => _AnimatedJoystickState();
}

class _AnimatedJoystickState extends State<AnimatedJoystick>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1500))
      ..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) => CustomPaint(
        size: Size(widget.size, widget.size * 0.82),
        painter: _JoystickPainter(t: _controller.value),
      ),
    );
  }
}

class _JoystickPainter extends CustomPainter {
  _JoystickPainter({required this.t});

  final double t;

  static const _topFace = Color(0xFF757575);
  static const _leftFace = Color(0xFF161616);
  static const _rightFace = Color(0xFF333333);
  static const _stick = Color(0xFFEDEDED);
  static const _accent = Color(0xFFE53935);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final top = Offset(w * 0.5, h * 0.06);
    final right = Offset(w * 0.96, h * 0.40);
    final bottom = Offset(w * 0.5, h * 0.74);
    final left = Offset(w * 0.04, h * 0.40);
    final depth = h * 0.20;
    Offset down(Offset o) => Offset(o.dx, o.dy + depth);

    // Isometric prism: dark left face, mid-tone right face, lighter top.
    final leftFacePath = Path()
      ..moveTo(left.dx, left.dy)
      ..lineTo(bottom.dx, bottom.dy)
      ..lineTo(down(bottom).dx, down(bottom).dy)
      ..lineTo(down(left).dx, down(left).dy)
      ..close();
    final rightFacePath = Path()
      ..moveTo(right.dx, right.dy)
      ..lineTo(bottom.dx, bottom.dy)
      ..lineTo(down(bottom).dx, down(bottom).dy)
      ..lineTo(down(right).dx, down(right).dy)
      ..close();
    final topFacePath = Path()
      ..moveTo(top.dx, top.dy)
      ..lineTo(right.dx, right.dy)
      ..lineTo(bottom.dx, bottom.dy)
      ..lineTo(left.dx, left.dy)
      ..close();

    canvas.drawPath(leftFacePath, Paint()..color = _leftFace);
    canvas.drawPath(rightFacePath, Paint()..color = _rightFace);
    canvas.drawPath(topFacePath, Paint()..color = _topFace);

    // Small side button, sitting on the top face.
    final buttonCenter = Offset.lerp(top, left, 0.55)! + Offset(0, h * 0.05);
    canvas.drawOval(
      Rect.fromCenter(center: buttonCenter, width: w * 0.14, height: h * 0.07),
      Paint()..color = _accent,
    );

    // The stick wiggles in a small circle, as if being actively steered.
    final angle = t * 2 * math.pi;
    final wiggle =
        Offset(math.cos(angle) * w * 0.09, math.sin(angle) * h * 0.05);
    final base = Offset(w * 0.5, h * 0.42);
    final stickTop = base + wiggle * 1.4 - Offset(0, h * 0.32);

    final stickPaint = Paint()
      ..color = _stick
      ..strokeWidth = w * 0.09
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(base, stickTop, stickPaint);
    canvas.drawCircle(stickTop, w * 0.14, Paint()..color = _accent);
    canvas.drawCircle(
      stickTop - Offset(w * 0.035, h * 0.035),
      w * 0.045,
      Paint()..color = Colors.white.withValues(alpha: 0.55),
    );
  }

  @override
  bool shouldRepaint(covariant _JoystickPainter oldDelegate) =>
      oldDelegate.t != t;
}
