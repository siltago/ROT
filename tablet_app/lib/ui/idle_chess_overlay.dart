import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';
import 'idle_game_skill.dart';

enum _Side { bob, rival }

class _ChessPiece {
  _ChessPiece(this.row, this.col, this.side, this.glyph, {this.isKing = false});
  int row;
  int col;
  final _Side side;
  final String glyph;
  final bool isKing;
}

/// A tiny self-playing chess doodle, in the same spirit as
/// [IdleSnakeOverlay] -- pieces shuffle one square at a time (no real
/// rules engine or opponent AI), just enough to read as "the robot idly
/// playing a match against itself". Runs until either king is captured
/// (a simulated win or loss) -- at which point [onFinished] fires so the
/// caller can start a fresh idle activity right away (it should always
/// look like the robot is doing something), and the result is reported
/// to the backend (see [fetchGameSkill]/[postGameResult] and
/// api/server.py's `/idle/game_skill`), which is what makes Bob's own
/// moves gradually less random over many matches. [maxDuration] is just
/// a generous safety net in case a match somehow never concludes, not
/// the normal way this ends. [onDismiss] is only for a genuine
/// interruption (the user calling the robot, or speaking).
class IdleChessOverlay extends StatefulWidget {
  const IdleChessOverlay({
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
  State<IdleChessOverlay> createState() => _IdleChessOverlayState();
}

class _IdleChessOverlayState extends State<IdleChessOverlay> {
  static const _size = 8;
  static const _backRank = ['♜', '♞', '♝', '♛', '♚', '♝', '♞', '♜'];
  final _random = math.Random();
  late List<_ChessPiece> _pieces;
  Timer? _tickTimer;
  Timer? _dismissTimer;
  bool _ended = false;
  // Whose turn it is -- alternated explicitly after every tick instead of
  // an independent coin flip each time, which could (and did) streak
  // several moves in a row for one side while the other sat still.
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
    _tickTimer = Timer.periodic(const Duration(milliseconds: 1600), (_) => _tick());
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
    unawaited(fetchGameSkill(widget.httpBaseUrl).then((skill) {
      if (mounted) _skill = skill;
    }));
  }

  void _resetGame() {
    _pieces = [];
    for (var col = 0; col < _size; col++) {
      _pieces.add(_ChessPiece(0, col, _Side.rival, _backRank[col], isKing: col == 4));
      _pieces.add(_ChessPiece(1, col, _Side.rival, '♟'));
      _pieces.add(_ChessPiece(6, col, _Side.bob, '♙'));
      // Same glyph shapes as the rival's back rank -- the color tint
      // (see _ChessPainter) is what tells the two sides apart, not glyph
      // choice, so there's no need for a separate white-piece glyph set.
      _pieces.add(_ChessPiece(7, col, _Side.bob, _backRank[col], isKing: col == 4));
    }
  }

  _ChessPiece? _at(int row, int col) {
    for (final p in _pieces) {
      if (p.row == row && p.col == col) return p;
    }
    return null;
  }

  void _tick() {
    if (_ended) return;
    // Give the side whose turn it is first crack at moving; if it truly
    // has nothing to do (boxed in), let the other side go instead of the
    // whole vignette stalling for a beat. Either way, possession swaps
    // for next time -- no more risk of one side streaking several moves
    // running while the other never gets picked.
    final other = _turn == _Side.bob ? _Side.rival : _Side.bob;
    if (!_tryMove(_turn)) _tryMove(other);
    _turn = other;
  }

  /// Attempts one move for [side]; returns whether a piece actually
  /// moved (and, via setState, already applied it). For Bob specifically
  /// (never the rival -- his skill shouldn't help the rival play better
  /// too), a roll against [_skill] first looks for *any* capturing move
  /// across his whole side and takes it outright, preferring the king if
  /// one's available -- rather than the fully-random per-piece walk
  /// below, which might stumble onto a capture or might not. Not a real
  /// evaluation function, just "captures more often as skill rises".
  bool _tryMove(_Side side) {
    if (side == _Side.bob && _skill > 0 && _random.nextDouble() < _skill) {
      if (_tryBestCapture()) return true;
    }
    return _tryRandomMove(side);
  }

  /// Scans every one of Bob's pieces for a legal capture (same move
  /// rules as [_tryRandomMove]'s inner loop) and takes the first one
  /// found, preferring one that captures the rival's king.
  bool _tryBestCapture() {
    final pieces = _pieces.where((p) => p.side == _Side.bob).toList();
    _ChessPiece? bestPiece;
    Offset? bestMove;
    var bestIsKingCapture = false;
    for (final piece in pieces) {
      final isPawn = piece.glyph == '♙';
      if (isPawn) continue; // pawns can't capture in this simplified sim
      for (final d in const [
        Offset(1, 0), Offset(-1, 0), Offset(0, 1), Offset(0, -1),
        Offset(1, 1), Offset(-1, -1), Offset(1, -1), Offset(-1, 1),
      ]) {
        final nr = piece.row + d.dy.toInt();
        final nc = piece.col + d.dx.toInt();
        if (nr < 0 || nr >= _size || nc < 0 || nc >= _size) continue;
        final occupant = _at(nr, nc);
        if (occupant == null || occupant.side == _Side.bob) continue;
        if (bestPiece == null || (occupant.isKing && !bestIsKingCapture)) {
          bestPiece = piece;
          bestMove = Offset(nc.toDouble(), nr.toDouble());
          bestIsKingCapture = occupant.isKing;
        }
      }
    }
    if (bestPiece == null || bestMove == null) return false;
    final occupant = _at(bestMove.dy.toInt(), bestMove.dx.toInt())!;
    setState(() {
      bestPiece!.row = bestMove!.dy.toInt();
      bestPiece.col = bestMove.dx.toInt();
      _pieces.remove(occupant);
    });
    // occupant is always a rival piece here (bob-side occupants are
    // skipped above) -- capturing the rival's king is a win, and ends
    // the match same as a loss does: either way it concluded, which is
    // what should chain to a new activity and count toward game_skill.
    if (occupant.isKing) {
      _endMatch();
    }
    return true;
  }

  bool _tryRandomMove(_Side side) {
    final forward = side == _Side.bob ? -1 : 1;
    final pieces = _pieces.where((p) => p.side == side).toList()..shuffle(_random);

    for (final piece in pieces) {
      final isPawn = piece.glyph == '♙' || piece.glyph == '♟';
      final directions = isPawn
          ? [Offset(0, forward.toDouble())]
          : ([
              const Offset(1, 0), const Offset(-1, 0),
              const Offset(0, 1), const Offset(0, -1),
              const Offset(1, 1), const Offset(-1, -1),
              const Offset(1, -1), const Offset(-1, 1),
            ]..shuffle(_random));

      for (final d in directions) {
        final nr = piece.row + d.dy.toInt();
        final nc = piece.col + d.dx.toInt();
        if (nr < 0 || nr >= _size || nc < 0 || nc >= _size) continue;
        final occupant = _at(nr, nc);
        if (occupant == null) {
          setState(() {
            piece.row = nr;
            piece.col = nc;
          });
          return true;
        }
        if (occupant.side != side && !isPawn) {
          setState(() {
            piece.row = nr;
            piece.col = nc;
            _pieces.remove(occupant);
          });
          // Either side's king falling concludes the match -- a win for
          // Bob is just as much "the match is over" as a loss is.
          if (occupant.isKing) {
            _endMatch();
          }
          return true;
        }
      }
    }
    return false;
  }

  /// A king fell (either side's) -- the match concluded, win or loss.
  /// Reports it (nudges game_skill up a small, slow amount server-side,
  /// fire-and-forget) and lets the vignette wind down as before.
  void _endMatch() {
    _ended = true;
    unawaited(postGameResult(widget.httpBaseUrl));
    Timer(const Duration(milliseconds: 600), widget.onFinished);
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
                    const Text('♞', style: TextStyle(fontSize: 16)),
                    const SizedBox(width: 6),
                    Text(
                      'jogando xadrez sozinho...',
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
                    painter: _ChessPainter(pieces: _pieces, color: color),
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

class _ChessPainter extends CustomPainter {
  _ChessPainter({required this.pieces, required this.color});

  final List<_ChessPiece> pieces;
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
      final tint = piece.side == _Side.bob ? color : const Color(0xFFE5734A);
      _paintPiece(canvas, center, cell, piece.glyph, tint);
    }
  }

  // Some Android font stacks resolve a few of these chess codepoints to
  // color-emoji presentation (and inconsistently so -- some pieces on the
  // same side get it, some don't), which paints its own fixed colors and
  // ignores TextStyle.color entirely; that's why pieces on the same side
  // used to show up in mismatched colors, and a text-presentation
  // variation selector alone wasn't enough to stop it. Painting the
  // glyph into an offscreen layer and recoloring that whole layer with a
  // srcIn color filter sidesteps the problem outright -- whatever colors
  // the font drew, only the glyph's own shape/alpha survives, flattened
  // to one solid tint, so every piece on a side always matches.
  void _paintPiece(Canvas canvas, Offset center, double cell, String glyph, Color tint) {
    final span = TextSpan(text: glyph, style: TextStyle(fontSize: cell * 0.72));
    final painter = TextPainter(text: span, textDirection: TextDirection.ltr)..layout();
    final offset = center - Offset(painter.width / 2, painter.height / 2);
    final bounds = Rect.fromLTWH(
      offset.dx - 6, offset.dy - 6, painter.width + 12, painter.height + 12);

    // Drop shadow pass, flattened to a soft black regardless of glyph
    // colors, painted slightly offset.
    canvas.saveLayer(bounds, Paint()..colorFilter = const ColorFilter.mode(Colors.black45, BlendMode.srcIn));
    painter.paint(canvas, offset + const Offset(0, 1.5));
    canvas.restore();

    // Piece pass, flattened to the side's solid tint.
    canvas.saveLayer(bounds, Paint()..colorFilter = ColorFilter.mode(tint.withValues(alpha: 0.95), BlendMode.srcIn));
    painter.paint(canvas, offset);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _ChessPainter oldDelegate) => true;
}
