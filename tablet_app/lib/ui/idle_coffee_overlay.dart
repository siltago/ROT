import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A "having a coffee" vignette -- the exact reference mug art (steam
/// already baked into the image) held low and centered, where the
/// robot's gaze (set by the caller, see [robot_app.dart]'s
/// `_coffeeGaze`) looks down at it, occasionally lifting toward the
/// mouth for a "sip". No card/label chrome, same bare staging as
/// [IdleReadingOverlay]. No "losing" condition; ends after [maxDuration]
/// (or [onDismiss] on interruption).
class IdleCoffeeOverlay extends StatefulWidget {
  const IdleCoffeeOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    this.maxDuration = const Duration(seconds: 25),
  });

  final RobotMood mood;
  final VoidCallback onDismiss;
  final VoidCallback onFinished;
  final Duration maxDuration;

  @override
  State<IdleCoffeeOverlay> createState() => _IdleCoffeeOverlayState();
}

class _IdleCoffeeOverlayState extends State<IdleCoffeeOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _sip;
  Timer? _dismissTimer;
  Timer? _sipTimer;

  @override
  void initState() {
    super.initState();
    _sip = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 700),
    );
    _scheduleSip();
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
  }

  void _scheduleSip() {
    _sipTimer = Timer(Duration(milliseconds: 3500 + math.Random().nextInt(3000)), () {
      if (!mounted) return;
      _sip.forward(from: 0).then((_) {
        if (mounted) _sip.reverse();
      });
      _scheduleSip();
    });
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    _sipTimer?.cancel();
    _sip.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const width = 156.0;
    return IgnorePointer(
      child: Align(
        alignment: Alignment.bottomCenter,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 76),
          child: AnimatedBuilder(
            animation: _sip,
            builder: (context, _) {
              // Lifted toward the "mouth" during a sip.
              final lift = _sip.value * 46.0;
              return Transform.translate(
                offset: Offset(0, -lift),
                child: Image.asset(
                  'assets/images/mug.png',
                  width: width,
                  fit: BoxFit.contain,
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
