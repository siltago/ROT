import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';

import '../robot/robot_display_state.dart';
import '../robot/robot_mood.dart';
import 'joystick_icon.dart';

double _lerp(double a, double b, double t) => a + (b - a) * t;

class RobotFaceWidget extends StatefulWidget {
  const RobotFaceWidget({
    super.key,
    required this.expression,
    required this.mood,
    required this.state,
    required this.microphoneLevel,
    required this.speechDetected,
    required this.trackedFace,
    this.isPlaying = false,
    this.readingGlasses = false,
    this.restingEyes = false,
    this.headphones = false,
    this.mouthOpen = 0.0,
    this.hueOverride,
  });

  final String expression;
  final RobotMood mood;
  final RobotDisplayState state;
  final double microphoneLevel;
  final bool speechDetected;
  final Offset? trackedFace;

  /// True while an idle self-entertainment animation is showing -- draws a
  /// small wiggling joystick under the eyes, echoing "I'm playing/focused".
  final bool isPlaying;

  /// True while the "reading" idle activity is showing -- draws a pair of
  /// reading glasses over the eyes, sized/positioned off the same
  /// measurements the eyes themselves use so they track any eye movement.
  final bool readingGlasses;

  /// True while the "resting" idle activity is showing -- squints the
  /// eyes to a sleepy half-open height instead of drawing anything extra.
  final bool restingEyes;

  /// True while the "humming" idle activity is showing -- draws a
  /// headphone band and ear cups over the head, same sizing approach as
  /// [readingGlasses].
  final bool headphones;

  /// 0 (closed, nothing drawn) to 1 (fully open) -- driven by the feed
  /// animation (see robot_app.dart's IdleFeedOverlay) while a piece of
  /// food dropped on /feed is being "eaten", so that actually reads as
  /// eating rather than just a food icon disappearing near the face.
  final double mouthOpen;

  /// When set, replaces the mood-driven eye color with this hue (0-360) at
  /// a fixed, pale saturation/lightness -- used to show wake-word state
  /// (listening passively vs actively) independent of emotional mood.
  /// Ignored while the state is error/offline, which keep their own colors.
  final double? hueOverride;

  @override
  State<RobotFaceWidget> createState() => _RobotFaceWidgetState();
}

class _RobotFaceWidgetState extends State<RobotFaceWidget>
    with TickerProviderStateMixin {
  static const _restingGaze = Offset(0.5, 0.5);
  static const _spring = SpringDescription(mass: 1, stiffness: 90, damping: 14);

  // 1.1s ping-pong used to breathe the eyes while speaking/thinking.
  late final AnimationController _speakPulse;
  // Slow, never-stopping drift so the face never looks perfectly frozen.
  late final AnimationController _idleDrift;
  // A single forward pass (0->1) is shaped into a close/open blink pulse.
  late final AnimationController _blink;
  late final AnimationController _gazeX;
  late final AnimationController _gazeY;

  RobotMood _moodFrom = const RobotMood();
  RobotMood _moodTo = const RobotMood();
  late final AnimationController _moodTransition;

  final _random = math.Random();
  Timer? _blinkTimer;

  @override
  void initState() {
    super.initState();
    _speakPulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat(reverse: true);
    _idleDrift = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 6400),
    )..repeat();
    _blink = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 130),
    );
    final start = widget.trackedFace ?? _restingGaze;
    _gazeX = AnimationController.unbounded(vsync: this, value: start.dx);
    _gazeY = AnimationController.unbounded(vsync: this, value: start.dy);

    _moodTo = widget.mood;
    _moodTransition = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..value = 1;

    _scheduleNextBlink();
  }

  void _scheduleNextBlink() {
    final delay = Duration(milliseconds: 10000 + _random.nextInt(10000));
    _blinkTimer = Timer(delay, () async {
      if (!mounted) return;
      await _blink.forward(from: 0);
      if (!mounted) return;
      if (_random.nextDouble() < 0.12) {
        await Future<void>.delayed(const Duration(milliseconds: 120));
        if (!mounted) return;
        await _blink.forward(from: 0);
      }
      if (mounted) _scheduleNextBlink();
    });
  }

  void _retargetGaze(Offset target) {
    _gazeX.animateWith(SpringSimulation(_spring, _gazeX.value, target.dx, 0));
    _gazeY.animateWith(SpringSimulation(_spring, _gazeY.value, target.dy, 0));
  }

  @override
  void didUpdateWidget(RobotFaceWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.trackedFace != widget.trackedFace) {
      _retargetGaze(widget.trackedFace ?? _restingGaze);
    }
    if (widget.mood.distanceTo(oldWidget.mood) > 0.02) {
      final current = _moodFrom.lerpTo(_moodTo, _moodTransition.value);
      _moodFrom = current;
      _moodTo = widget.mood;
      _moodTransition.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _blinkTimer?.cancel();
    _speakPulse.dispose();
    _idleDrift.dispose();
    _blink.dispose();
    _gazeX.dispose();
    _gazeY.dispose();
    _moodTransition.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final backgroundColor = widget.state == RobotDisplayState.error
        ? const Color(0xFF260A11)
        : const Color(0xFF070B16);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 350),
      color: backgroundColor,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final baseEyeHeight = math.min(
            constraints.maxHeight * 0.5,
            constraints.maxWidth * 0.34,
          );
          final baseEyeWidth = baseEyeHeight * 0.42;
          final gap = baseEyeWidth * 1.15;

          return Stack(
            children: [
              Center(
                child: AnimatedBuilder(
                  animation: Listenable.merge([
                    _speakPulse,
                    _idleDrift,
                    _blink,
                    _gazeX,
                    _gazeY,
                    _moodTransition,
                  ]),
                  builder: (context, _) {
                    final mood = _moodFrom.lerpTo(_moodTo,
                        Curves.easeOutCubic.transform(_moodTransition.value));
                    final pulse = _speakPulse.value;
                    final blinkPulse =
                        math.sin(math.pi * _blink.value.clamp(0.0, 1.0));
                    final idleT = _idleDrift.value;
                    // Resting slows the breathing cycle down; the eyes
                    // themselves switch to a drawn closed-lid curve (see
                    // _ClosedEyePainter, used by _Eye when `closed` is
                    // true) instead of the usual capsule shrunk down --
                    // a flattened capsule reads as a small circle or a
                    // flat bar, never an actually curved closed eye.
                    final breathing = widget.restingEyes
                        ? 1 + math.sin(idleT * 2 * math.pi * 0.4) * 0.02
                        : 1 + math.sin(idleT * 2 * math.pi) * 0.012;
                    final restingWidthScale = widget.restingEyes ? 1.15 : 1.0;

                    final leftLook = _computeEyeLook(
                      isLeft: true,
                      mood: mood,
                      state: widget.state,
                      blink: blinkPulse,
                      speakPulse: pulse,
                      baseWidth: baseEyeWidth * restingWidthScale,
                      baseHeight: baseEyeHeight * breathing,
                      hueOverride: widget.hueOverride,
                    );
                    final rightLook = _computeEyeLook(
                      isLeft: false,
                      mood: mood,
                      state: widget.state,
                      blink: blinkPulse,
                      speakPulse: pulse,
                      baseWidth: baseEyeWidth * restingWidthScale,
                      baseHeight: baseEyeHeight * breathing,
                      hueOverride: widget.hueOverride,
                    );

                    final maxDx = baseEyeWidth * 2.6;
                    final maxDy = baseEyeHeight * 0.5;
                    final idleJitterX = math.sin(idleT * 2 * math.pi * 0.6) *
                        baseEyeWidth *
                        0.025;
                    final idleJitterY = math.cos(idleT * 2 * math.pi * 0.9) *
                        baseEyeHeight *
                        0.012;
                    final dx = (_gazeX.value - 0.5) * maxDx + idleJitterX;
                    final dy = (_gazeY.value - 0.5) * maxDy + idleJitterY;

                    return Transform.translate(
                      offset: Offset(dx, dy),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Stack(
                            alignment: Alignment.center,
                            // The Stack's own size now comes solely from
                            // the eyes Row (the accessory images below are
                            // Positioned.fill, exempt from sizing it) --
                            // but that means it's a small box, and an
                            // accessory image bigger than that box would
                            // get clipped to it under the default
                            // Clip.hardEdge. Clip.none lets them render at
                            // their real (larger) size, centered on it.
                            clipBehavior: Clip.none,
                            children: [
                              // Paint order (a Stack paints later
                              // children on top of earlier ones):
                              // headphones behind the eyes (the band
                              // arcs over the head, cups beside it --
                              // it reads as worn under/around the face),
                              // then the eyes, then glasses in front of
                              // the eyes (they sit on the nose, in front
                              // of the face).
                              if (widget.headphones)
                                Positioned.fill(
                                  child: IgnorePointer(
                                    child: OverflowBox(
                                      maxWidth: double.infinity,
                                      maxHeight: double.infinity,
                                      // The exact reference headphones
                                      // art, not a drawn approximation --
                                      // same sizing approach as
                                      // glasses.png, just much wider so
                                      // the ear cups clear well past the
                                      // eye row's edges instead of
                                      // landing on top of the eyes.
                                      child: Transform.translate(
                                        // Negative (up), not positive --
                                        // the cups need to land level
                                        // with the eyes, not below them.
                                        offset: Offset(0, -baseEyeHeight * 0.35),
                                        child: Image.asset(
                                          'assets/images/headphones.png',
                                          width: (baseEyeWidth * 2 + gap) * 2.0,
                                          fit: BoxFit.contain,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  _Eye(look: leftLook, closed: widget.restingEyes),
                                  SizedBox(width: gap),
                                  _Eye(look: rightLook, closed: widget.restingEyes),
                                ],
                              ),
                              if (widget.readingGlasses)
                                // Positioned.fill + an inner OverflowBox
                                // keeps this out of the Stack's own size
                                // calculation entirely -- otherwise an
                                // accessory image wider/taller than the
                                // eye row (as headphones especially are)
                                // inflates the Stack itself, which then
                                // shoves the whole face down within the
                                // Column below it. A plain non-Positioned
                                // child would do exactly that. OverflowBox
                                // (not Center) matters here too: Center
                                // alone still caps the child's max size to
                                // the tiny Positioned.fill box it's inside
                                // -- exactly the "glasses shrank" bug this
                                // replaced -- where OverflowBox actually
                                // lets the child lay out at its own
                                // requested (larger) size.
                                Positioned.fill(
                                  child: IgnorePointer(
                                    child: OverflowBox(
                                      maxWidth: double.infinity,
                                      maxHeight: double.infinity,
                                      // The exact reference glasses art,
                                      // not a drawn approximation --
                                      // sized off the same eye-row
                                      // measurements so it still tracks
                                      // the eyes, but wider than that row
                                      // (glasses read wider than the eyes
                                      // themselves) and nudged down
                                      // toward the bottom of the eyes,
                                      // like glasses slid part-way down
                                      // the nose.
                                      child: Transform.translate(
                                        offset: Offset(0, baseEyeHeight * 0.36),
                                        child: Image.asset(
                                          'assets/images/glasses.png',
                                          width: (baseEyeWidth * 2 + gap) * 1.55,
                                          fit: BoxFit.contain,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              if (widget.mouthOpen > 0)
                                Positioned.fill(
                                  child: IgnorePointer(
                                    child: OverflowBox(
                                      maxWidth: double.infinity,
                                      maxHeight: double.infinity,
                                      child: Transform.translate(
                                        offset: Offset(0, baseEyeHeight * 0.95),
                                        child: CustomPaint(
                                          size: Size(baseEyeWidth * 1.5, baseEyeHeight * 0.55),
                                          painter: _MouthPainter(
                                            openness: widget.mouthOpen,
                                            color: leftLook.color,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                            ],
                          ),
                          const SizedBox(height: 28),
                          if (widget.isPlaying) ...[
                            const AnimatedJoystick(),
                            const SizedBox(height: 16),
                          ],
                          Text(
                            widget.state.label,
                            style: TextStyle(
                              color: _accentColor.withValues(alpha: 0.62),
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 3.5,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
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
                  color:
                      widget.speechDetected ? Colors.greenAccent : _accentColor,
                  backgroundColor: Colors.white10,
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Color get _accentColor {
    if (widget.state == RobotDisplayState.error) return Colors.redAccent;
    if (widget.state == RobotDisplayState.offline) return Colors.blueGrey;
    return Colors.white;
  }
}

/// Continuous eye geometry for one eye, derived from the emotional mood
/// vector plus a handful of transient signals (blink, speak pulse, display
/// state). Nothing here is a per-expression template: every field is a
/// number computed from continuous inputs, so the shape can land anywhere
/// between "neutral" and "furious" rather than snapping between fixed poses.
class _EyeLook {
  const _EyeLook({
    required this.width,
    required this.height,
    required this.rotation,
    required this.color,
  });

  final double width;
  final double height;
  final double rotation;
  final Color color;
}

_EyeLook _computeEyeLook({
  required bool isLeft,
  required RobotMood mood,
  required RobotDisplayState state,
  required double blink,
  required double speakPulse,
  required double baseWidth,
  required double baseHeight,
  double? hueOverride,
}) {
  final width = baseWidth * (1 + mood.curiosity * 0.12);

  // Closing an eye (tired, squinting, blinking, sleeping) always shrinks its
  // height and nothing else, so the shape stays a rounded capsule -- never a
  // flat-cut "eyelid" -- all the way down to a thin rounded sliver.
  double openness = 1.0;
  // Tired -> heavier eyes, all the time (not just during the special
  // "resting" idle vignette) -- pushed further than before (0.55 -> 0.65)
  // so real exhaustion is visible on the main face, not just a subtle
  // squint nobody notices, but not so far that ordinary moderate
  // tiredness reads as fully asleep on a face that isn't even doing the
  // "resting" vignette.
  openness -= (1 - mood.energy) * 0.65;
  openness -= mood.irritation * 0.12; // irritation -> slight squint
  if (mood.valence > 0.5) {
    openness += (mood.valence - 0.5) * 0.18; // bright/happy -> a touch wider
  }
  final curiousLift = isLeft ? mood.curiosity * 0.03 : mood.curiosity * 0.09;
  openness += curiousLift; // curiosity -> wide-eyed, one brow raised more

  switch (state) {
    case RobotDisplayState.sleeping:
      openness = 0.08;
      break;
    case RobotDisplayState.listening:
      openness += 0.12;
      break;
    case RobotDisplayState.thinking:
      if (!isLeft) openness -= 0.35;
      break;
    case RobotDisplayState.speaking:
      openness *= 1 + speakPulse * 0.05;
      break;
    case RobotDisplayState.offline:
    case RobotDisplayState.error:
    case RobotDisplayState.idle:
    case RobotDisplayState.acting:
      break;
  }

  // Blink closes the eye regardless of mood/state (sleeping is already shut).
  if (state != RobotDisplayState.sleeping) {
    openness = openness * (1 - blink) + 0.05 * blink;
  }

  final height = baseHeight * openness.clamp(0.05, 1.2);

  // Whole-eye tilt: irritation furrows inward-down (angry), low valence
  // droops inward-up (sad); mirrored so both eyes tilt toward the "nose".
  final angryTilt = mood.irritation * 0.24;
  final sadTilt = (0.5 - mood.valence).clamp(0.0, 1.0) * 0.16;
  final tilt = angryTilt - sadTilt;
  final rotation = isLeft ? -tilt : tilt;

  return _EyeLook(
    width: width,
    height: height,
    rotation: rotation,
    color: _moodColor(mood, state, hueOverride: hueOverride),
  );
}

Color _moodColor(RobotMood mood, RobotDisplayState state,
    {double? hueOverride}) {
  if (state == RobotDisplayState.error) return Colors.redAccent;
  if (state == RobotDisplayState.offline) return Colors.blueGrey.shade200;
  if (hueOverride != null) {
    // Wake-state color: a plain, pale tint rather than the full mood
    // formula -- the point is a clear at-a-glance signal (listening
    // passively vs actively), not emotional nuance.
    return HSLColor.fromAHSL(1, hueOverride % 360, 0.4, 0.75).toColor();
  }

  const hueNeutral = 200.0;
  const hueHappy = 45.0;
  const hueSad = 235.0;
  const hueAngry = 5.0;

  final hueMood = mood.valence >= 0.5
      ? _lerp(hueNeutral, hueHappy, (mood.valence - 0.5) * 2)
      : _lerp(hueSad, hueNeutral, mood.valence * 2);
  final hue = _lerp(hueMood, hueAngry, mood.irritation) % 360;
  final saturation = _lerp(0.25, 0.85, mood.energy).clamp(0.0, 1.0);
  final lightness = _lerp(0.55, 0.75, mood.curiosity).clamp(0.0, 1.0);
  return HSLColor.fromAHSL(1, hue, saturation, lightness).toColor();
}

class _Eye extends StatelessWidget {
  const _Eye({required this.look, this.closed = false});

  final _EyeLook look;

  /// True for the "resting" idle activity -- draws a gently downward-
  /// curved closed-lid line (see [_ClosedEyePainter]) instead of the
  /// usual capsule. A capsule just squashed down on height reads as a
  /// small circle or a flat bar, never an actually curved closed eye.
  final bool closed;

  @override
  Widget build(BuildContext context) {
    final w = look.width;
    final h = look.height;

    if (closed) {
      return Transform.rotate(
        angle: look.rotation,
        child: SizedBox(
          width: w,
          height: math.max(h, w * 0.5),
          child: CustomPaint(painter: _ClosedEyePainter(color: look.color)),
        ),
      );
    }

    // Corner radius is capped by the shape's own smaller side, so the eye is
    // always a rounded capsule -- including while shrinking down to a thin
    // rounded sliver for a blink -- and the glow (same box) never drifts out
    // of sync with the visible shape the way a separate overlay would.
    final radius = math.min(w, h) / 2;

    return Transform.rotate(
      angle: look.rotation,
      child: SizedBox(
        width: w,
        height: h,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: look.color,
            borderRadius: BorderRadius.circular(radius),
            boxShadow: [
              BoxShadow(
                color: look.color.withValues(alpha: 0.4),
                blurRadius: 24,
                spreadRadius: 2,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A thin line curving gently downward in the middle (like a shallow
/// "⌣") -- a closed/sleepy eyelid, drawn as an actual curve rather than a
/// flattened capsule.
class _ClosedEyePainter extends CustomPainter {
  _ClosedEyePainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final midY = size.height * 0.42;
    final dip = w * 0.22;
    final path = Path()
      ..moveTo(w * 0.06, midY)
      ..quadraticBezierTo(w * 0.5, midY + dip, w * 0.94, midY);
    final strokeWidth = w * 0.09;
    canvas.drawPath(
      path,
      Paint()
        ..color = color.withValues(alpha: 0.4)
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth * 2.4
        ..strokeCap = StrokeCap.round
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10),
    );
    canvas.drawPath(
      path,
      Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(covariant _ClosedEyePainter oldDelegate) => oldDelegate.color != color;
}

/// A small rounded mouth that opens (a wide oval) and closes (a thin
/// line) with [openness] -- driven by the feed animation's "chomp" beats
/// so eating a dropped food actually reads as eating.
class _MouthPainter extends CustomPainter {
  _MouthPainter({required this.openness, required this.color});

  final double openness;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final o = openness.clamp(0.0, 1.0);
    final width = size.width * (0.55 + o * 0.15);
    final height = size.height * (0.08 + o * 0.92);
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: width,
      height: height,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, Radius.circular(height / 2)),
      Paint()..color = const Color(0xFF06090F),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, Radius.circular(height / 2)),
      Paint()
        ..color = color.withValues(alpha: 0.55)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.6,
    );
  }

  @override
  bool shouldRepaint(covariant _MouthPainter oldDelegate) =>
      oldDelegate.openness != openness || oldDelegate.color != color;
}
