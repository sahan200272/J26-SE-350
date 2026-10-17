import 'dart:typed_data';

/// PCM16LE bytes for [samples].
Uint8List pcmBytes(List<int> samples) {
  final data = ByteData(samples.length * 2);
  for (var i = 0; i < samples.length; i++) {
    data.setInt16(i * 2, samples[i], Endian.little);
  }
  return data.buffer.asUint8List();
}

/// [count] samples of a constant [value].
Uint8List constantPcm(int count, [int value = 1000]) =>
    pcmBytes(List.filled(count, value));

/// Deterministic test signal covering the whole 16-bit range, including
/// values whose high byte has the sign bit set.
List<int> rampSamples(int count, {int start = 0}) => [
  for (var i = start; i < start + count; i++) ((i * 7919) % 65536) - 32768,
];
