import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';
import 'idle_game_skill.dart';

/// A tiny self-playing checkers doodle, in the same spirit as
/// [IdleSnakeOverlay] -- diagonal moves and occasional jump-captures, no
/// real rules engine or opponent AI, just enough to read as "the robot
/// idly playing a match against itself". Runs until either side runs low
/// on pieces (a simulated win or loss) -- at which point [onFinished]
/// fires so the caller can start a fresh idle activity right away (it
/// should always look like the robot is doing something), and the
/// result is reported to the backend (see [fetchGameSkill]/
/// [postGameResult] and api/server.py's `/idle/game_skill`), which is
/// what makes Bob's own moves gradually less random over many matches.
/// [maxDuration] is just a generous safety net in case a match somehow
/// never concludes, not the normal way this ends. [onDismiss] is only for
/// a genuine interruption (the user calling the robot, or speaking).
class IdleCheckersOverlay extends StatefulWidget {
  const IdleCheckersOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    required this.httpBaseUrl,
    this.maxDuration = const Duration(seconds: 150),
  });

  final RobotMood mood;
  final VoidCallback onDismiss;
  final VoidCallback onFinished;
  final String httpBaseUrl;
  final Duration maxDuration;

  @override
  State<IdleCheckersOverlay> createState() => _IdleCheckersOverlayState();
}

enum _Side { bob, rival }

class _Piece {
  _Piece(this.row, this.col, this.side);
  int row;
  int col;
  final _Side side;
}

class _IdleCheckersOverlayState extends State<IdleCheckersOverlay> {
  static const _size = 8;
  final _random = math.Random();
  late List<_Piece> _pieces;
  Timer? _tickTimer;
  Timer? _dismissTimer;
  bool _ended = false;
  // Whose turn it is -- alternated explicitly after every tick instead
  // of an independent coin flip each time, which could streak several
  // moves in a row for one side while the other sat still.
  _Side _turn = _Side.rival;
  // How much less random Bob's own moves are -- fetched once per match
  // from /idle/game_skill (see api/server.py), 0 if that fails so this
  // always degrades to the original fully-random behavior rather than
  // erroring.
  double _skill = 0;

  @override
  void initState() {
    super.initState();
    _resetGame();
    _tickTimer = Timer.periodic(const Duration(milliseconds: 1400), (_) => _tick());
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
    unawaited(fetchGameSkill(widget.httpBaseUrl).then((skill) {
      if (mounted) _skill = skill;
    }));
  }

  void _resetGame() {
    _pieces = [];
    for (var row = 0; row < 3; row++) {
      for (var col = 0; col < _size; col++) {
        if ((row + col).isOdd) _pieces.add(_Piece(row, col, _Side.rival));
      }
    }
    for (var row = _size - 3; row < _size; row++) {
      for (var col = 0; col < _size; col++) {
        if ((row + col).isOdd) _pieces.add(_Piece(row, col, _Side.bob));
      }
    }
  }

  bool _occupied(int row, int col) =>
      _pieces.any((p) => p.row == row && p.col == col);

  _Piece? _at(int row, int col) {
    for (final p in _pieces) {
      if (p.row == row && p.col == col) return p;
    }
    return null;
  }

  void _tick() {
    if (_ended) return;
    // Give the side whose turn it is first crack at moving; if it truly
    // has nothing to do, let the other side go instead of the whole
    // vignette stalling for a beat. Either way, possession swaps for
    // next time -- no risk of one side streaking several moves while the
    // other never gets picked.
    final other = _turn == _Side.bob ? _Side.rival : _Side.bob;
    if (!_tryMove(_turn)) _tryMove(other);
    _turn = other;
  }

  /// Attempts one move (or jump-capture) for [side]; returns whether a
  /// piece actually moved (and, via setState, already applied it). For
  /// Bob specifically (never the rival), a roll against [_skill] first
  /// looks for *any* jump-capture across his whole side and takes it
  /// outright, rather than the fully-random per-piece walk below, which
  /// might stumble onto a capture or might not.
  bool _tryMove(_Side side) {
    if (side == _Side.bob && _skill > 0 && _random.nextDouble() < _skill) {
      if (_tryBestCapture()) return true;
    }
    return _tryRandomMove(side);
  }

  /// Scans every one of Bob's pieces for a legal jump-capture (same
  /// rules as [_tryRandomMove]'s inner loop) and takes the first one
  /// found.
  bool _tryBestCapture() {
    const direction = -1;
    final pieces = _pieces.where((p) => p.side == _Side.bob).toList();
    for (final piece in pieces) {
      for (final dc in const [-1, 1]) {
        final nr = piece.row + direction;
        final nc = piece.col + dc;
        if (nr < 0 || nr >= _size || nc < 0 || nc >= _size) continue;
        final blocker = _at(nr, nc);
        if (blocker == null || blocker.side == _Side.bob) continue;
        final jr = nr + direction;
        final jc = nc + dc;
        if (jr < 0 || jr >= _size || jc < 0 || jc >= _size) continue;
        if (_occupied(jr, jc)) continue;
        setState(() {
          piece.row = jr;
          piece.col = jc;
          _pieces.remove(blocker);
        });
        _maybeEnd();
        return true;
      }
    }
    return false;
  }

  bool _tryRandomMove(_Side side) {
    final direction = side == _Side.bob ? -1 : 1;
    final candidates = _pieces.where((p) => p.side == side).toList()
      ..shuffle(_random);

    for (final piece in candidates) {
      final steps = [-1, 1]..shuffle(_random);
      for (final dc in steps) {
        final nr = piece.row + direction;
        final nc = piece.col + dc;
        if (nr < 0 || nr >= _size || nc < 0 || nc >= _size) continue;
        final blocker = _at(nr, nc);
        if (blocker == null) {
          setState(() {
            piece.row = nr;
            piece.col = nc;
          });
          return true;
        }
        if (blocker.side != side) {
          // A jump-capture, if the landing square beyond is empty.
          final jr = nr + direction;
          final jc = nc + dc;
          if (jr < 0 || jr >= _size || jc < 0 || jc >= _size) continue;
          if (!_occupied(jr, jc)) {
            setState(() {
              piece.row = jr;
              piece.col = jc;
              _pieces.remove(blocker);
            });
            _maybeEnd();
            return true;
          }
        }
      }
    }
    return false;
  }

  void _maybeEnd() {
    if (_ended) return;
    final bobCount = _pieces.where((p) => p.side == _Side.bob).length;
    final rivalCount = _pieces.where((p) => p.side == _Side.rival).length;
    // "Winning"/"losing" is simulated, not a real evaluation -- just
    // enough pieces down on either side that ending the vignette here
    // reads as a natural conclusion. Either way it's a concluded match,
    // which is what should chain to a new activity and count toward
    // game_skill.
    if (bobCount <= 3 || rivalCount <= 3) {
      _ended = true;
      unawaited(postGameResult(widget.httpBaseUrl));
      Timer(const Duration(milliseconds: 500), widget.onFinished);
    }
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
        HSLColor.fromAHSL(1, 190 + widget.mood.curiosity * 60, 0.65, 0.68)
            .toColor();
    const width = 280.0;
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
                  Color.lerp(const Color(0xE60B1020), color, 0.12)!,
                ],
              ),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: color.withValues(alpha: 0.55), width: 1.4),
              boxShadow: [
                BoxShadow(color: color.withValues(alpha: 0.28), blurRadius: 24, spreadRadius: 1),
                const BoxShadow(color: Colors.black45, blurRadius: 16, offset: Offset(0, 6)),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    const Text('⚫', style: TextStyle(fontSize: 16)),
                    const SizedBox(width: 6),
                    Text(
                      'jogando damas sozinho...',
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
                  height: width - 20,
                  child: CustomPaint(
                    painter: _CheckersPainter(pieces: _pieces, color: color),
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

class _CheckersPainter extends CustomPainter {
  _CheckersPainter({required this.pieces, required this.color});

  final List<_Piece> pieces;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    const n = 8;
    final cell = size.width / n;
    for (var row = 0; row < n; row++) {
      for (var col = 0; col < n; col++) {
        final dark = (row + col).isOdd;
        final rect = Rect.fromLTWH(col * cell, row * cell, cell, cell);
        canvas.drawRect(
          rect,
          Paint()..color = dark ? const Color(0xFF1C2333) : const Color(0xFF262E44),
        );
      }
    }
    for (final piece in pieces) {
      final center = Offset((piece.col + 0.5) * cell, (piece.row + 0.5) * cell);
      final fill = piece.side == _Side.bob
          ? color
          : const Color(0xFFE5734A);
      canvas.drawCircle(center, cell * 0.38, Paint()..color = Colors.black26);
      canvas.drawCircle(
        center,
        cell * 0.34,
        Paint()..color = fill.withValues(alpha: 0.92),
      );
      canvas.drawCircle(
        center,
        cell * 0.34,
        Paint()
          ..color = Colors.white.withValues(alpha: 0.25)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _CheckersPainter oldDelegate) => true;
}
