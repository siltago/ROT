import 'package:flutter/material.dart';

import '../robot/robot_mood.dart';

/// A small, always-visible panel showing Bob's 5 "bichinho virtual"
/// attributes as bars -- distinct from [DebugPanel] (the big, technical,
/// toggle-only one): this one is for casually keeping an eye on how
/// tired/hungry/bored/irritated/happy he is, at a glance, all the time.
class AttributesPanel extends StatelessWidget {
  const AttributesPanel({super.key, required this.mood});

  final RobotMood mood;

  @override
  Widget build(BuildContext context) {
    final tiredness = 1 - mood.energy;
    return IgnorePointer(
      child: Container(
        width: 168,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: const Color(0xCC0B1020),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _bar('😴', 'cansaço', tiredness, const Color(0xFF7DA9FF)),
            _bar('🍽️', 'fome', mood.hunger, const Color(0xFFE5A24A)),
            _bar('😐', 'tédio', mood.boredom, const Color(0xFF9E9E9E)),
            _bar('😠', 'irritação', mood.irritation, const Color(0xFFE5574A)),
            _bar('🙂', 'humor', mood.valence, const Color(0xFF4AE58E)),
          ],
        ),
      ),
    );
  }

  Widget _bar(String emoji, String label, double value, Color color) {
    final clamped = value.clamp(0.0, 1.0);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 12)),
          const SizedBox(width: 6),
          SizedBox(
            width: 52,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white70, fontSize: 10.5),
            ),
          ),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: SizedBox(
                height: 6,
                child: Stack(
                  children: [
                    Container(color: Colors.white.withValues(alpha: 0.10)),
                    FractionallySizedBox(
                      widthFactor: clamped,
                      child: Container(color: color),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
