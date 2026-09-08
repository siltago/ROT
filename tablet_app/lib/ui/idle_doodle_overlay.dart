import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A "doodling on paper" vignette -- a sheet of paper held low and
/// centered, where the robot's gaze (set by the caller, see
/// [robot_app.dart]'s `_doodleGaze`) looks down at it while a real,
/// recognizable little drawing (a house, a star, a cat...) grows across
/// it stroke by stroke, then the sheet quietly resets to a new subject.
///
/// The subject is picked by one cheap GET to [httpBaseUrl]'s
/// `/idle/doodle_subject` (no LLM call -- the backend just picks from a
/// small curated list) so it varies without costing anything per draw;
/// if that request fails or names something this widget doesn't have a
/// drawing for, it falls back to a random abstract squiggle instead of
/// blocking or erroring. No "losing" condition; ends after [maxDuration]
/// (or [onDismiss] on interruption).
class IdleDoodleOverlay extends StatefulWidget {
  const IdleDoodleOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    required this.httpBaseUrl,
    this.maxDuration = const Duration(seconds: 28),
  });

  final RobotMood mood;
  final VoidCallback onDismiss;
  final VoidCallback onFinished;
  final String httpBaseUrl;
  final Duration maxDuration;

  @override
  State<IdleDoodleOverlay> createState() => _IdleDoodleOverlayState();
}

class _IdleDoodleOverlayState extends State<IdleDoodleOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _draw;
  final _random = math.Random();
  late List<List<Offset>> _strokes;
  Timer? _dismissTimer;

  @override
  void initState() {
    super.initState();
    _strokes = [_generateSquiggle()];
    _draw = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4200),
    )..addStatusListener((status) {
        if (status == AnimationStatus.completed && mounted) {
          unawaited(_nextDrawing());
        }
      });
    _draw.forward();
    unawaited(_fetchSubject());
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
  }

  Future<void> _nextDrawing() async {
    if (!mounted) return;
    await _fetchSubject();
    if (!mounted) return;
    _draw.forward(from: 0);
  }

  Future<void> _fetchSubject() async {
    final subject = await _requestDoodleSubject(widget.httpBaseUrl);
    if (!mounted) return;
    final drawing = subject != null ? _subjectDrawings[subject] : null;
    setState(() {
      _strokes = drawing ?? [_generateSquiggle()];
    });
  }

  List<Offset> _generateSquiggle() {
    final points = <Offset>[];
    var x = 0.08, y = 0.4 + _random.nextDouble() * 0.2;
    points.add(Offset(x, y));
    while (x < 0.92) {
      x += 0.06 + _random.nextDouble() * 0.07;
      y = (y + (_random.nextDouble() - 0.5) * 0.3).clamp(0.14, 0.8);
      points.add(Offset(x.clamp(0.0, 0.95), y));
    }
    return points;
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    _draw.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const width = 170.0;
    return IgnorePointer(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 82),
          child: SizedBox(
            width: width,
            height: width * 0.68,
            child: AnimatedBuilder(
              animation: _draw,
              builder: (context, _) => CustomPaint(
                painter: _DoodlePainter(strokes: _strokes, progress: _draw.value),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One cheap, tokenless request for what to draw next. Any failure
/// (offline, timeout, unexpected response) is swallowed and treated the
/// same as "no subject" -- the caller falls back to an abstract squiggle
/// rather than this ever being visible as an error.
Future<String?> _requestDoodleSubject(String httpBaseUrl) async {
  final client = HttpClient();
  try {
    final request = await client
        .getUrl(Uri.parse('$httpBaseUrl/idle/doodle_subject'))
        .timeout(const Duration(seconds: 3));
    final response = await request.close().timeout(const Duration(seconds: 3));
    if (response.statusCode != 200) return null;
    final body = await response.transform(utf8.decoder).join();
    final decoded = jsonDecode(body);
    if (decoded is Map && decoded['subject'] is String) {
      return decoded['subject'] as String;
    }
    return null;
  } catch (_) {
    return null;
  } finally {
    client.close(force: true);
  }
}

/// Points around an ellipse, as a closed polyline -- the building block
/// used for every round-ish shape below (sun, cat head, fish body...)
/// since strokes are plain straight-segment polylines.
List<Offset> _ellipse(Offset center, double rx, double ry, {int segments = 20}) {
  return [
    for (var i = 0; i <= segments; i++)
      center +
          Offset(
            rx * math.cos(2 * math.pi * i / segments),
            ry * math.sin(2 * math.pi * i / segments),
          ),
  ];
}

/// A small library of recognizable line-drawings, each a list of strokes
/// (a stroke is drawn as one connected polyline; the pen "lifts" between
/// strokes), in a normalized 0..1 square. Kept in sync by hand with the
/// backend's `_DOODLE_SUBJECTS` list (api/server.py).
final Map<String, List<List<Offset>>> _subjectDrawings = {
  'casa': [
    // Square base.
    [const Offset(0.2, 0.55), const Offset(0.2, 0.85), const Offset(0.8, 0.85), const Offset(0.8, 0.55)],
    // Triangle roof.
    [const Offset(0.14, 0.58), const Offset(0.5, 0.22), const Offset(0.86, 0.58)],
    // Door.
    [const Offset(0.44, 0.85), const Offset(0.44, 0.65), const Offset(0.58, 0.65), const Offset(0.58, 0.85)],
  ],
  'estrela': [
    [
      const Offset(0.5, 0.15), const Offset(0.61, 0.42), const Offset(0.9, 0.42),
      const Offset(0.66, 0.6), const Offset(0.76, 0.88), const Offset(0.5, 0.7),
      const Offset(0.24, 0.88), const Offset(0.34, 0.6), const Offset(0.1, 0.42),
      const Offset(0.39, 0.42), const Offset(0.5, 0.15),
    ],
  ],
  'coracao': [
    [
      const Offset(0.5, 0.85), const Offset(0.18, 0.55), const Offset(0.14, 0.35),
      const Offset(0.26, 0.18), const Offset(0.42, 0.22), const Offset(0.5, 0.36),
      const Offset(0.58, 0.22), const Offset(0.74, 0.18), const Offset(0.86, 0.35),
      const Offset(0.82, 0.55), const Offset(0.5, 0.85),
    ],
  ],
  'sol': [
    _ellipse(const Offset(0.5, 0.5), 0.22, 0.22, segments: 24),
    for (var i = 0; i < 8; i++)
      [
        const Offset(0.5, 0.5) + Offset(math.cos(i * math.pi / 4), math.sin(i * math.pi / 4)) * 0.26,
        const Offset(0.5, 0.5) + Offset(math.cos(i * math.pi / 4), math.sin(i * math.pi / 4)) * 0.42,
      ],
  ],
  'nuvem': [
    [
      const Offset(0.14, 0.62), const Offset(0.14, 0.5), const Offset(0.24, 0.4),
      const Offset(0.34, 0.42), const Offset(0.4, 0.3), const Offset(0.56, 0.28),
      const Offset(0.68, 0.38), const Offset(0.82, 0.4), const Offset(0.88, 0.52),
      const Offset(0.84, 0.62), const Offset(0.14, 0.62),
    ],
  ],
  'arvore': [
    // Trunk.
    [const Offset(0.46, 0.85), const Offset(0.46, 0.58), const Offset(0.54, 0.58), const Offset(0.54, 0.85)],
    // Canopy.
    _ellipse(const Offset(0.5, 0.38), 0.28, 0.24, segments: 22),
  ],
  'gato': [
    _ellipse(const Offset(0.5, 0.55), 0.26, 0.22, segments: 22),
    [const Offset(0.3, 0.4), const Offset(0.34, 0.2), const Offset(0.42, 0.36)],
    [const Offset(0.7, 0.4), const Offset(0.66, 0.2), const Offset(0.58, 0.36)],
    [const Offset(0.18, 0.58), const Offset(0.4, 0.58)],
    [const Offset(0.6, 0.58), const Offset(0.82, 0.58)],
  ],
  'peixe': [
    _ellipse(const Offset(0.42, 0.5), 0.26, 0.16, segments: 20),
    [const Offset(0.66, 0.5), const Offset(0.88, 0.34), const Offset(0.88, 0.66), const Offset(0.66, 0.5)],
    _ellipse(const Offset(0.28, 0.46), 0.025, 0.025, segments: 10),
  ],
  'flor': [
    for (var i = 0; i < 5; i++)
      _ellipse(
        const Offset(0.5, 0.4) +
            Offset(math.cos(2 * math.pi * i / 5), math.sin(2 * math.pi * i / 5)) * 0.16,
        0.13, 0.09, segments: 14,
      ),
    // Stem.
    [const Offset(0.5, 0.5), const Offset(0.5, 0.86)],
  ],
  'robo': [
    // Head.
    [const Offset(0.32, 0.32), const Offset(0.68, 0.32), const Offset(0.68, 0.62), const Offset(0.32, 0.62), const Offset(0.32, 0.32)],
    // Antenna.
    [const Offset(0.5, 0.32), const Offset(0.5, 0.18)],
    _ellipse(const Offset(0.5, 0.15), 0.03, 0.03, segments: 8),
    // Eyes.
    _ellipse(const Offset(0.42, 0.46), 0.03, 0.03, segments: 8),
    _ellipse(const Offset(0.58, 0.46), 0.03, 0.03, segments: 8),
    // Body.
    [const Offset(0.36, 0.62), const Offset(0.64, 0.62), const Offset(0.64, 0.82), const Offset(0.36, 0.82), const Offset(0.36, 0.62)],
  ],
};

class _DoodlePainter extends CustomPainter {
  _DoodlePainter({required this.strokes, required this.progress});

  final List<List<Offset>> strokes;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final paperRect = Rect.fromLTWH(0, 0, size.width, size.height);
    canvas.drawRRect(
      RRect.fromRectAndRadius(paperRect, const Radius.circular(6)),
      Paint()..color = const Color(0xFFF4EFE2),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(paperRect, const Radius.circular(6)),
      Paint()
        ..color = const Color(0xFFD9D0BA)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4,
    );

    final totalPoints = strokes.fold<int>(0, (sum, s) => sum + s.length);
    if (totalPoints < 2) return;
    var budget = (totalPoints * progress).clamp(1, totalPoints).toDouble();

    final linePaint = Paint()
      ..color = const Color(0xFF3A3630)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.2
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;

    Offset? tip;
    for (final stroke in strokes) {
      if (budget <= 0) break;
      final visibleCount = math.min(stroke.length, budget.ceil());
      if (visibleCount < 1) continue;
      final path = Path()
        ..moveTo(stroke[0].dx * size.width, stroke[0].dy * size.height);
      for (var i = 1; i < visibleCount; i++) {
        path.lineTo(stroke[i].dx * size.width, stroke[i].dy * size.height);
      }
      canvas.drawPath(path, linePaint);
      tip = stroke[visibleCount - 1];
      budget -= stroke.length;
    }

    // The pencil tip, tracking just ahead of the last visible point.
    if (tip != null && progress < 1) {
      canvas.drawCircle(
        Offset(tip.dx * size.width, tip.dy * size.height),
        2.6,
        Paint()..color = const Color(0xFF6B6155),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _DoodlePainter oldDelegate) =>
      oldDelegate.progress != progress || oldDelegate.strokes != strokes;
}
