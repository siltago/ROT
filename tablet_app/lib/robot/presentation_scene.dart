class PresentationScene {
  const PresentationScene({
    required this.kind,
    required this.variant,
    required this.data,
    required this.persistent,
    this.duration,
  });

  final String kind;
  final String variant;
  final Map<String, dynamic> data;
  final bool persistent;
  final Duration? duration;

  factory PresentationScene.fromPayload(Map<String, dynamic> payload) {
    final rawData = payload['data'];
    final durationMs = (payload['duration_ms'] as num?)?.toInt();
    return PresentationScene(
      kind: '${payload['kind'] ?? 'unknown'}'.toLowerCase(),
      variant: '${payload['variant'] ?? 'default'}'.toLowerCase(),
      data: rawData is Map
          ? Map<String, dynamic>.from(rawData)
          : const <String, dynamic>{},
      persistent: payload['persistent'] == true,
      duration: durationMs == null ? null : Duration(milliseconds: durationMs),
    );
  }
}
