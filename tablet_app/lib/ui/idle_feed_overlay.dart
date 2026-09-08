import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Food keys the /feed page can send, each with a fallback emoji for
/// when the matching asset (assets/images/food/<key>.png) hasn't been
/// dropped in yet -- keeps this working end-to-end regardless of which
/// real images exist at any given moment.
const Map<String, String> foodEmojiFallback = {
  'apple': '🍎',
  'pizza': '🍕',
  'cookie': '🍪',
  'burger': '🍔',
  'chocolate': '🍫',
};

/// Shown the instant a `feed_animation` message arrives (someone fed Bob
/// through the /feed web page) -- not one of the idle self-entertainment
/// vignettes (never in `_idleActivityKinds`, never picked by
/// `_pickIdleActivity`), just a short reaction dropped on top of
/// whatever else is happening. The food drops down toward the mouth,
/// which opens for a "chomp" bite (see [RobotFaceWidget.mouthOpen], fed
/// by [onMouthOpen]), then a "+" flourish floats up and the whole thing
/// fades out on its own -- no onDismiss/onFinished needed, [onDone]
/// always fires once, a couple seconds in.
class IdleFeedOverlay extends StatefulWidget {
  const IdleFeedOverlay({
    super.key,
    required this.food,
    required this.onDone,
    this.onMouthOpen,
  });

  /// A key like "apple" (matches assets/images/food/apple.png) -- falls
  /// back to [foodEmojiFallback] if that key is unknown or the asset
  /// isn't present yet.
  final String food;
  final VoidCallback onDone;
  final ValueChanged<double>? onMouthOpen;

  @override
  State<IdleFeedOverlay> createState() => _IdleFeedOverlayState();
}

class _IdleFeedOverlayState extends State<IdleFeedOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  Timer? _doneTimer;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..forward();
    _doneTimer = Timer(const Duration(milliseconds: 2100), widget.onDone);
  }

  @override
  void dispose() {
    _doneTimer?.cancel();
    _controller.dispose();
    widget.onMouthOpen?.call(0);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 90),
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, _) {
              final t = _controller.value;
              // 0.0-0.35 drop in, 0.35-0.5 chomp squash, 0.5-1.0 fade with
              // a "+" rising alongside.
              final dropT = (t / 0.35).clamp(0.0, 1.0);
              final drop = Curves.easeOutBack.transform(dropT);
              final y = -60 * (1 - drop);
              final chompT = ((t - 0.35) / 0.15).clamp(0.0, 1.0);
              final squash = 1 - math.sin(chompT * math.pi) * 0.35;
              final fadeT = ((t - 0.55) / 0.45).clamp(0.0, 1.0);
              final opacity = 1 - fadeT;
              final plusY = -fadeT * 40;

              // Mouth: opens while the food approaches, holds open
              // through the squash, then snaps shut right at the bite
              // and stays closed for the rest.
              double mouthValue;
              if (t < 0.35) {
                mouthValue = dropT;
              } else if (t < 0.5) {
                mouthValue = 1.0;
              } else {
                final closeT = ((t - 0.5) / 0.08).clamp(0.0, 1.0);
                mouthValue = 1.0 - closeT;
              }
              // Deferred to after this frame -- onMouthOpen typically
              // triggers setState on an ancestor (robot_app.dart), which
              // isn't safe to call synchronously from here, mid-build.
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (mounted) widget.onMouthOpen?.call(mouthValue);
              });

              return Opacity(
                opacity: opacity,
                child: Stack(
                  alignment: Alignment.center,
                  clipBehavior: Clip.none,
                  children: [
                    Transform.translate(
                      offset: Offset(0, y),
                      child: Transform.scale(
                        scaleX: 1 / squash,
                        scaleY: squash,
                        child: _FoodImage(food: widget.food),
                      ),
                    ),
                    if (fadeT > 0)
                      Transform.translate(
                        offset: Offset(28, -10 + plusY),
                        child: Text(
                          '+1',
                          style: TextStyle(
                            color: const Color(0xFF2EE6A6).withValues(alpha: opacity),
                            fontWeight: FontWeight.w800,
                            fontSize: 18,
                          ),
                        ),
                      ),
                  ],
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// The real reference image for [food] (assets/images/food/<food>.png)
/// when it's actually been added, falling back to an emoji otherwise --
/// so the feed animation works end-to-end for every food key regardless
/// of which images exist yet.
class _FoodImage extends StatelessWidget {
  const _FoodImage({required this.food});

  final String food;

  @override
  Widget build(BuildContext context) {
    final fallback = foodEmojiFallback[food] ?? '🍽️';
    return Image.asset(
      'assets/images/food/$food.png',
      width: 64,
      height: 64,
      fit: BoxFit.contain,
      errorBuilder: (context, error, stackTrace) =>
          Text(fallback, style: const TextStyle(fontSize: 56)),
    );
  }
}
