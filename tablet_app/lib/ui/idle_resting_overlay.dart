import 'dart:async';

import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A quiet "just resting" vignette. All the actual effect happens on the
/// face itself (see [RobotFaceWidget.restingEyes] -- squinted eyes, a
/// slowed breathing cycle) rather than anything drawn here; this widget
/// exists only to hold the timers, matching every other idle activity's
/// shape. No "losing" condition; ends after [maxDuration] (or
/// [onDismiss] on interruption).
class IdleRestingOverlay extends StatefulWidget {
  const IdleRestingOverlay({
    super.key,
    required this.mood,
    required this.onDismiss,
    required this.onFinished,
    this.maxDuration = const Duration(seconds: 26),
  });

  final RobotMood mood;
  final VoidCallback onDismiss;
  final VoidCallback onFinished;
  final Duration maxDuration;

  @override
  State<IdleRestingOverlay> createState() => _IdleRestingOverlayState();
}

class _IdleRestingOverlayState extends State<IdleRestingOverlay> {
  Timer? _dismissTimer;

  @override
  void initState() {
    super.initState();
    _dismissTimer = Timer(widget.maxDuration, widget.onFinished);
  }

  @override
  void dispose() {
    _dismissTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
