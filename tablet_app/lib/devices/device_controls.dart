import 'package:flutter/services.dart';

/// Small hardware controls Bob can use on the tablet he lives on -- media
/// volume and screen brightness, as 0..100 percentages. Backed by the
/// native channel in MainActivity.kt. Every call fails safe (returns null)
/// so a missing/failed native side never breaks the app.
class DeviceControls {
  static const MethodChannel _channel = MethodChannel('robotbrain/device');

  /// Current {volume, brightness} in percent, or null if unavailable.
  static Future<Map<String, int>?> getState() async {
    try {
      final raw = await _channel.invokeMapMethod<String, dynamic>('getState');
      if (raw == null) return null;
      return {
        'volume': (raw['volume'] as num?)?.round() ?? 0,
        'brightness': (raw['brightness'] as num?)?.round() ?? 0,
      };
    } catch (_) {
      return null;
    }
  }

  /// Applies a `device_control` payload from the backend
  /// ({control: volume|brightness, mode: set|step, value: int}) and
  /// returns the resulting state, or null if nothing could be applied.
  static Future<Map<String, int>?> apply(Map<String, dynamic> payload) async {
    final control = payload['control'] as String?;
    final mode = payload['mode'] as String?;
    final value = (payload['value'] as num?)?.round();
    if (value == null || (control != 'volume' && control != 'brightness')) {
      return null;
    }
    try {
      final current = await getState();
      if (current == null) return null;
      final target =
          (mode == 'step' ? current[control]! + value : value).clamp(0, 100);
      await _channel.invokeMethod<int>(
        control == 'volume' ? 'setVolume' : 'setBrightness',
        {'percent': target},
      );
      return await getState();
    } catch (_) {
      return null;
    }
  }
}
