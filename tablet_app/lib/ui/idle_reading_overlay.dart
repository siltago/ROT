import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A small open-book doodle, pinned low and centered so it reads as
/// something held in front of the robot while its gaze (set by the
/// caller, see [robot_app.dart]'s `_readingGaze`) looks down toward it --
/// paired with [RobotFaceWidget.readingGlasses] for the glasses-on-the-
/// face half of the effect. No "losing" condition (there's nothing to
/// win or lose at reading) -- after [maxDuration] it calls [onFinished]
/// so the caller can start a fresh idle activity right away, or
/// [onDismiss] fires early on any sign of user interaction like every
/// other idle activity.
///
/// Once per session, fires a one-off `POST /reading/learn` (see
/// [httpBaseUrl]) -- a cheap, tokenless "lesson" that nudges one real
/// PersonalityTraits field a tiny amount and sets up what the next
/// "doodle" idle session tries to draw, so reading and doodling read as
/// connected instead of two unrelated vignettes.
class IdleReadingOverlay extends StatefulWidget {
  const IdleReadingOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    required this.httpBaseUrl,
    this.maxDuration = const Duration(seconds: 30),
  });

  final RobotMood mood;
  final VoidCallback onDismiss;
  final VoidCallback onFinished;
  final String httpBaseUrl;
  final Duration maxDuration;

  @override
  State<IdleReadingOverlay> createState() => _IdleReadingOverlayState();
}

class _IdleReadingOverlayState extends State<IdleReadingOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pageTurn;
  Timer? _dismissTimer;
  Timer? _pageTimer;

  @override
  void initState() {
    super.initState();
    _pageTurn = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 650),
    );
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
    _schedulePageTurn();
    unawaited(_postReadingLearn(widget.httpBaseUrl));
  }

  void _schedulePageTurn() {
    _pageTimer = Timer(Duration(milliseconds: 2600 + math.Random().nextInt(1800)), () {
      if (!mounted) return;
      _pageTurn.forward(from: 0).then((_) {
        if (mounted) _pageTurn.reset();
      });
      _schedulePageTurn();
    });
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    _pageTimer?.cancel();
    _pageTurn.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // No card/label chrome here on purpose -- just the book itself,
    // floating low and centered where the robot's gaze is looking, same
    // as the reference art the robot's "reading" pose is meant to match.
    const width = 190.0;
    return IgnorePointer(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 84),
          child: SizedBox(
            width: width,
            height: width * 0.66,
            child: AnimatedBuilder(
              animation: _pageTurn,
              builder: (context, _) => CustomPaint(
                painter: _BookPainter(pageTurn: _pageTurn.value),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// One cheap, tokenless "lesson" per reading session -- see
/// api/server.py's `/reading/learn`. Any failure (offline, timeout) is
/// swallowed; a missed lesson just means no personality nudge this
/// session, never a visible error.
Future<void> _postReadingLearn(String httpBaseUrl) async {
  final client = HttpClient();
  try {
    final request = await client
        .postUrl(Uri.parse('$httpBaseUrl/reading/learn'))
        .timeout(const Duration(seconds: 3));
    await request.close().timeout(const Duration(seconds: 3));
  } catch (_) {
    // Ignored on purpose -- see doc comment above.
  } finally {
    client.close(force: true);
  }
}

/// Drawn to match the reference storybook icon -- a squat open book with
/// a stepped, layered brown cover (like pixel-art bevel shading), cream
/// pages carrying ruled "text" lines that taper as they near the spine, a
/// small diamond ornament in each far corner, and a short base the spine
/// rests on.
class _BookPainter extends CustomPainter {
  _BookPainter({required this.pageTurn});

  final double pageTurn;

  static const _coverOuter = Color(0xFF3E2415);
  static const _coverMid = Color(0xFF6B4226);
  static const _coverLight = Color(0xFF8B5A34);
  static const _page = Color(0xFFF3E7CE);
  static const _pageShade = Color(0xFFE3D3AE);
  static const _rule = Color(0xFFC9AF80);

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    // Short base the spine rests on.
    final baseRect = Rect.fromLTWH(w * 0.42, h * 0.93, w * 0.16, h * 0.05);
    canvas.drawRect(baseRect, Paint()..color = _coverOuter);

    final bookRect = Rect.fromLTWH(w * 0.04, h * 0.08, w * 0.92, h * 0.86);
    final midX = bookRect.left + bookRect.width / 2;
    final spineDip = h * 0.10;

    // Three stepped cover layers (darkest outermost), each slightly
    // inset from the last -- the "pixel bevel" look of the reference,
    // approximated with flat steps instead of literal pixels.
    void coverStep(double inset, Color fillColor, {double dip = 0}) {
      final r = Rect.fromLTWH(bookRect.left + inset, bookRect.top + inset,
          bookRect.width - inset * 2, bookRect.height - inset * 1.6);
      final mx = r.left + r.width / 2;
      final path = Path()
        ..moveTo(r.left, r.top)
        ..lineTo(mx - r.width * 0.06, r.top)
        ..lineTo(mx, r.top + dip)
        ..lineTo(mx + r.width * 0.06, r.top)
        ..lineTo(r.right, r.top)
        ..lineTo(r.right, r.bottom)
        ..lineTo(r.left, r.bottom)
        ..close();
      canvas.drawPath(path, Paint()..color = fillColor);
    }

    coverStep(0, _coverOuter);
    coverStep(w * 0.025, _coverMid, dip: spineDip * 0.3);
    coverStep(w * 0.05, _coverLight, dip: spineDip * 0.55);

    // The pages themselves -- a flat rectangle, top edge straight like
    // the cover's, not dipped down toward the spine.
    final pagesInset = w * 0.09;
    final pagesRect = Rect.fromLTWH(
      bookRect.left + pagesInset,
      bookRect.top + pagesInset * 0.55,
      bookRect.width - pagesInset * 2,
      bookRect.height - pagesInset * 1.5,
    );
    canvas.drawRect(pagesRect, Paint()..color = _page);
    // A soft shade along the bottom edge, suggesting page stacking
    // without drawing each individual sheet.
    canvas.drawRect(
      pagesRect,
      Paint()
        ..color = _pageShade
        ..style = PaintingStyle.stroke
        ..strokeWidth = w * 0.015,
    );

    // Ruled "text" lines -- all the same length and aligned to the same
    // inner/outer edges on each half, like actual ruled text rows rather
    // than tapering ones.
    final rulePaint = Paint()
      ..color = _rule
      ..strokeWidth = h * 0.028
      ..strokeCap = StrokeCap.butt;
    for (final side in [-1, 1]) {
      final inner = midX + side * pagesRect.width * 0.06;
      final outer = midX + side * pagesRect.width * 0.40;
      for (var i = 0; i < 6; i++) {
        final y = pagesRect.top + h * 0.09 + i * h * 0.075;
        if (y > pagesRect.bottom - h * 0.03) continue;
        canvas.drawLine(Offset(inner, y), Offset(outer, y), rulePaint);
      }
    }

    // A small diamond ornament in the far corners, like the reference.
    void diamond(Offset center, double r) {
      final path = Path()
        ..moveTo(center.dx, center.dy - r)
        ..lineTo(center.dx + r, center.dy)
        ..lineTo(center.dx, center.dy + r)
        ..lineTo(center.dx - r, center.dy)
        ..close();
      canvas.drawPath(path, Paint()..color = _pageShade);
    }

    diamond(Offset(pagesRect.left + pagesRect.width * 0.14, pagesRect.top + h * 0.08),
        w * 0.02);
    diamond(Offset(pagesRect.right - pagesRect.width * 0.14, pagesRect.bottom - h * 0.08),
        w * 0.02);

    // A straight spine crease down the middle, matching the pages'
    // otherwise flat, straight edges.
    canvas.drawLine(
      Offset(midX, pagesRect.top),
      Offset(midX, pagesRect.bottom),
      Paint()
        ..color = _pageShade
        ..strokeWidth = w * 0.012,
    );

    // A page mid-turn: a soft highlight sweeping across one half, just
    // enough motion to read as "still reading" rather than a frozen
    // photo of a book.
    if (pageTurn > 0 && pageTurn < 1) {
      final t = pageTurn;
      final sweepX = midX + pagesRect.width * 0.5 * (1 - 2 * t).abs();
      final curl = Path()
        ..moveTo(midX, pagesRect.top)
        ..lineTo(sweepX, pagesRect.top)
        ..lineTo(sweepX, pagesRect.bottom)
        ..lineTo(midX, pagesRect.bottom)
        ..close();
      canvas.drawPath(
        curl,
        Paint()..color = Colors.white.withValues(alpha: 0.30 * (1 - (t - 0.5).abs() * 2)),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _BookPainter oldDelegate) =>
      oldDelegate.pageTurn != pageTurn;
}
