import 'dart:async';

import 'package:flutter/foundation.dart';

class MicrophoneService {
  final StreamController<double> _levelController = StreamController.broadcast();

  Stream<double> get levelStream => _levelController.stream;

  Future<void> start() async {
    // Minimal placeholder for real microphone stream.
    // In a production app, use record or similar plugin and compute RMS level.
    unawaited(
      Stream<void>.periodic(const Duration(milliseconds: 200), (_) => null).listen((_) {
        final nextValue = _simulateVolume();
        _levelController.add(nextValue);
      }),
    );
  }

  double _simulateVolume() {
    final value = (DateTime.now().millisecondsSinceEpoch % 1000) / 1000.0;
    return value < 0.8 ? value : 0.8;
  }

  void stop() {
    _levelController.close();
  }
}
