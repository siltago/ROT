import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A tiny self-playing "snake" doodle shown when the robot is idle -- the
/// AIBO-style "entertains itself" behavior. It plays against itself with a
/// simple greedy heuristic (no AI/network involved) and is drawn faint and
/// small so it reads as the robot idly doodling, not a game taking over the
/// screen. Dismissed by the caller on any sign of user interaction, or on
/// its own after [maxDuration].
class IdleSnakeOverlay extends StatefulWidget {
  const IdleSnakeOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    this.maxDuration = const Duration(seconds: 20),
  });

  final RobotMood mood;
  // User interrupted (spoke, called the robot) -- clears the overlay
  // entirely.
  final VoidCallback onDismiss;
  // The vignette ran its natural course (here, just maxDuration -- snake
  // never really "loses") -- the caller should start a fresh idle
  // activity instead of leaving the face blank.
  final VoidCallback onFinished;
  final Duration maxDuration;

  @override
  State<IdleSnakeOverlay> createState() => _IdleSnakeOverlayState();
}

class _IdleSnakeOverlayState extends State<IdleSnakeOverlay> {
  static const _columns = 14;
  static const _rows = 10;
  static const _directions = [
    Offset(1, 0),
    Offset(-1, 0),
    Offset(0, 1),
    Offset(0, -1)
  ];

  final _random = math.Random();
  late List<Offset> _body;
  late Offset _direction;
  late Offset _food;
  Timer? _tickTimer;
  Timer? _dismissTimer;

  @override
  void initState() {
    super.initState();
    _resetGame();
    _tickTimer =
        Timer.periodic(const Duration(milliseconds: 230), (_) => _tick());
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
  }

  void _resetGame() {
    final startY = (_rows / 2).floor().toDouble();
    _body = [Offset(6, startY), Offset(5, startY), Offset(4, startY)];
    _direction = const Offset(1, 0);
    _food = _spawnFood();
  }

  Offset _spawnFood() {
    while (true) {
      final candidate = Offset(
        _random.nextInt(_columns).toDouble(),
        _random.nextInt(_rows).toDouble(),
      );
      if (!_body.contains(candidate)) return candidate;
    }
  }

  bool _isSafe(Offset cell) {
    if (cell.dx < 0 || cell.dx >= _columns || cell.dy < 0 || cell.dy >= _rows) {
      return false;
    }
    // The tail cell will vacate this tick unless the snake is about to eat.
    final willGrow = cell == _food;
    final body = willGrow ? _body : _body.sublist(0, _body.length - 1);
    return !body.contains(cell);
  }

  void _tick() {
    final head = _body.first;
    final reverse = Offset(-_direction.dx, -_direction.dy);
    final candidates = _directions.where((d) => d != reverse).toList();
    final safe = candidates.where((d) => _isSafe(head + d)).toList();

    if (safe.isEmpty) {
      setState(_resetGame);
      return;
    }

    safe.sort((a, b) {
      final da = (head + a - _food).distanceSquared;
      final db = (head + b - _food).distanceSquared;
      if (da != db) return da.compareTo(db);
      // Prefer to keep going straight when it's equally good -- less jittery.
      return a == _direction ? -1 : (b == _direction ? 1 : 0);
    });

    setState(() {
      _direction = safe.first;
      final newHead = head + _direction;
      final ateFood = newHead == _food;
      _body = [newHead, ..._body];
      if (ateFood) {
        _food = _spawnFood();
      } else {
        _body.removeLast();
      }
    });
  }

  @override
  void dispose() {
    _tickTimer?.cancel();
    _dismissTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color =
        HSLColor.fromAHSL(1, _hueFromMood(widget.mood), 0.65, 0.68).toColor();
    const width = 280.0;
    // Pinned to a corner (not centered) so it never competes with -- or hides
    // behind -- the much larger eyes; a dark backing panel keeps it readable
    // regardless of what mood color is behind it.
    return IgnorePointer(
      child: Align(
        alignment: Alignment.topLeft,
        child: Padding(
          padding: const EdgeInsets.only(left: 24, top: 24),
          child: Container(
            width: width,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  const Color(0xE60B1020),
                  Color.lerp(const Color(0xE60B1020), color, 0.12)!
                ],
              ),
              borderRadius: BorderRadius.circular(18),
              border:
                  Border.all(color: color.withValues(alpha: 0.55), width: 1.4),
              boxShadow: [
                BoxShadow(
                    color: color.withValues(alpha: 0.28),
                    blurRadius: 24,
                    spreadRadius: 1),
                const BoxShadow(
                    color: Colors.black45,
                    blurRadius: 16,
                    offset: Offset(0, 6)),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    const Text('🐍', style: TextStyle(fontSize: 16)),
                    const SizedBox(width: 6),
                    Text(
                      'se distraindo...',
                      style: TextStyle(
                        color: color.withValues(alpha: 0.85),
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.1,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: width - 20,
                  height: (width - 20) * _rows / _columns,
                  child: CustomPaint(
                    painter: _SnakePainter(
                        body: _body,
                        food: _food,
                        columns: _columns,
                        rows: _rows,
                        color: color),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

double _hueFromMood(RobotMood mood) => 190 + mood.curiosity * 60;

class _SnakePainter extends CustomPainter {
  _SnakePainter({
    required this.body,
    required this.food,
    required this.columns,
    required this.rows,
    required this.color,
  });

  final List<Offset> body;
  final Offset food;
  final int columns;
  final int rows;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final cellWidth = size.width / columns;
    final cellHeight = size.height / rows;
    final cell = math.min(cellWidth, cellHeight);

    for (var i = body.length - 1; i >= 0; i--) {
      final segment = body[i];
      final isHead = i == 0;
      // Fades from a bright head to a dimmer tail -- reads as one directional
      // creature instead of a row of identical squares.
      final fade = 1 - (i / body.length) * 0.55;
      final rect = Rect.fromLTWH(segment.dx * cellWidth,
              segment.dy * cellHeight, cellWidth, cellHeight)
          .deflate(cell * (isHead ? 0.06 : 0.14));
      final paint = Paint()..color = color.withValues(alpha: fade);
      canvas.drawRRect(
          RRect.fromRectAndRadius(rect, Radius.circular(cell * 0.4)), paint);
      if (isHead) {
        final eyePaint = Paint()..color = const Color(0xFF0B1020);
        final eyeOffset = Offset(rect.width * 0.22, rect.height * 0.22);
        canvas.drawCircle(rect.center - eyeOffset, cell * 0.07, eyePaint);
        canvas.drawCircle(rect.center + Offset(eyeOffset.dx, -eyeOffset.dy),
            cell * 0.07, eyePaint);
      }
    }

    final foodCenter =
        Offset((food.dx + 0.5) * cellWidth, (food.dy + 0.5) * cellHeight);
    final glowPaint = Paint()
      ..color = color.withValues(alpha: 0.45)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6);
    canvas.drawCircle(foodCenter, cell * 0.42, glowPaint);
    canvas.drawCircle(foodCenter, cell * 0.26,
        Paint()..color = Colors.white.withValues(alpha: 0.95));
  }

  @override
  bool shouldRepaint(covariant _SnakePainter oldDelegate) =>
      oldDelegate.body != body ||
      oldDelegate.food != food ||
      oldDelegate.color != color;
}
