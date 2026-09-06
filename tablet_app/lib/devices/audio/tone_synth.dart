import 'dart:math' as math;
import 'dart:typed_data';

/// Synthesizes a short "wolf whistle" tone as a WAV byte buffer, mono 16-bit
/// PCM. No audio asset is bundled with the app -- this is pure DSP math, so
/// the idle whistle behavior costs nothing beyond a few milliseconds of CPU.
Uint8List buildWhistleWav(
    {int sampleRate = 22050, double durationSeconds = 0.6}) {
  final sampleCount = (sampleRate * durationSeconds).round();
  final samples = Int16List(sampleCount);

  // Frequency sweeps up then down (a simple whistle contour). Frequency is
  // integrated into phase (rather than recomputed per-sample from t) so the
  // waveform stays continuous -- no clicks at the frequency turning point.
  var phase = 0.0;
  for (var i = 0; i < sampleCount; i++) {
    final t = i / sampleCount; // 0..1 across the whole tone
    final frequency = t < 0.45
        ? _lerp(650, 1900, t / 0.45)
        : _lerp(1900, 950, (t - 0.45) / 0.55);
    phase += 2 * math.pi * frequency / sampleRate;

    // Fade in/out so the clip starts and ends at zero amplitude.
    final envelope = math.min(1.0, math.min(t / 0.05, (1 - t) / 0.08));
    samples[i] =
        (math.sin(phase) * envelope * 0.7 * 32767).round().clamp(-32768, 32767);
  }

  return _wrapAsWav(samples, sampleRate);
}

double _lerp(double a, double b, double t) => a + (b - a) * t;

Uint8List _wrapAsWav(Int16List samples, int sampleRate) {
  const channels = 1;
  const bitsPerSample = 16;
  final byteRate = sampleRate * channels * bitsPerSample ~/ 8;
  const blockAlign = channels * bitsPerSample ~/ 8;
  final dataSize = samples.lengthInBytes;

  final buffer = BytesBuilder();
  void writeString(String value) => buffer.add(value.codeUnits);
  void writeUint32(int value) {
    final bytes = ByteData(4)..setUint32(0, value, Endian.little);
    buffer.add(bytes.buffer.asUint8List());
  }

  void writeUint16(int value) {
    final bytes = ByteData(2)..setUint16(0, value, Endian.little);
    buffer.add(bytes.buffer.asUint8List());
  }

  writeString('RIFF');
  writeUint32(36 + dataSize);
  writeString('WAVE');
  writeString('fmt ');
  writeUint32(16);
  writeUint16(1); // PCM
  writeUint16(channels);
  writeUint32(sampleRate);
  writeUint32(byteRate);
  writeUint16(blockAlign);
  writeUint16(bitsPerSample);
  writeString('data');
  writeUint32(dataSize);
  buffer.add(samples.buffer.asUint8List());

  return buffer.toBytes();
}
