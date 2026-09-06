/// Continuous emotional signal driving the face, mirroring the backend's
/// `EmotionalState` (see `emotions/state.py`). Kept as plain 0.0-1.0 floats so
/// the face can render a continuously varying shape/color instead of picking
/// from a fixed template per discrete expression.
class RobotMood {
  const RobotMood({
    this.valence = 0.5,
    this.energy = 0.6,
    this.irritation = 0.05,
    this.curiosity = 0.6,
  });

  final double valence;
  final double energy;
  final double irritation;
  final double curiosity;

  /// Parses the numeric fields from a `set_expression` payload, falling back
  /// to [previous] field-by-field so older/partial payloads (or a payload
  /// that only carries the legacy `expression` string) don't reset the mood.
  factory RobotMood.fromPayload(
    Map<String, dynamic> payload, {
    RobotMood previous = const RobotMood(),
  }) {
    double field(String key, double fallback) {
      final value = payload[key];
      if (value is num) return value.toDouble().clamp(0.0, 1.0);
      return fallback;
    }

    return RobotMood(
      valence: field('valence', previous.valence),
      energy: field('energy', previous.energy),
      irritation: field('irritation', previous.irritation),
      curiosity: field('curiosity', previous.curiosity),
    );
  }

  RobotMood lerpTo(RobotMood target, double t) {
    double lerp(double a, double b) => a + (b - a) * t;
    return RobotMood(
      valence: lerp(valence, target.valence),
      energy: lerp(energy, target.energy),
      irritation: lerp(irritation, target.irritation),
      curiosity: lerp(curiosity, target.curiosity),
    );
  }

  /// How different this mood is from [other], 0 (identical) to ~2 (opposite
  /// on every axis). Used to decide whether a change is worth reacting to.
  double distanceTo(RobotMood other) {
    return (valence - other.valence).abs() +
        (energy - other.energy).abs() +
        (irritation - other.irritation).abs() +
        (curiosity - other.curiosity).abs();
  }

  @override
  String toString() =>
      'RobotMood(valence: ${valence.toStringAsFixed(2)}, energy: ${energy.toStringAsFixed(2)}, '
      'irritation: ${irritation.toStringAsFixed(2)}, curiosity: ${curiosity.toStringAsFixed(2)})';
}
