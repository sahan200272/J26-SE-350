import 'dart:math';

import 'package:echo_vault/capture/pcm_framer.dart';

import 'pcm.dart';

/// Synthetic test signals in whole 32 ms frames (512 samples at 16 kHz).

List<int> silence(int frames) => List.filled(frames * kFrameSamples, 0);

/// Sine at [hz] with peak [amplitude]; RMS level = 20·log10(a/√2/32768),
/// e.g. 3277 → −23.0 dBFS.
List<int> tone(int frames, {int amplitude = 3277, double hz = 440}) => [
  for (var i = 0; i < frames * kFrameSamples; i++)
    (amplitude * sin(2 * pi * hz * i / 16000)).round(),
];

/// Speech-like: 320 ms of tone, 64 ms of silence, repeated. Real speech has
/// such dips; a perfectly steady tone longer than the EnergyVad noise window
/// (3 s) would instead be learned as background.
List<int> speechLike(int frames, {int amplitude = 3277}) => [
  for (var f = 0; f < frames; f++)
    ...(f % 12 < 10 ? tone(1, amplitude: amplitude) : silence(1)),
];

/// Gaussian noise with RMS level [dbfs] (seeded, so reproducible).
List<int> noise(int frames, {double dbfs = -60, int seed = 1}) {
  final rng = Random(seed);
  final sigma = 32768 * pow(10, dbfs / 20);
  double gauss() {
    final u1 = 1 - rng.nextDouble();
    final u2 = rng.nextDouble();
    return sqrt(-2 * log(u1)) * cos(2 * pi * u2);
  }

  return [
    for (var i = 0; i < frames * kFrameSamples; i++)
      (sigma * gauss()).round().clamp(-32768, 32767),
  ];
}

/// [a] + [b] sample by sample (clamped), for bursts on top of noise.
List<int> mix(List<int> a, List<int> b) => [
  for (var i = 0; i < a.length; i++) (a[i] + b[i]).clamp(-32768, 32767),
];

/// Frames recording runs one after another through a real [PcmFramer], so
/// run indices, audio offsets and padded last frames are as in the app.
class FrameSource {
  final _framer = PcmFramer();

  /// Frames [samples] as the next run, starting at [sessionStart] (default:
  /// right after the previous run's audio, i.e. no pause on the timeline).
  List<PcmFrame> run(List<int> samples, {Duration? sessionStart}) {
    final start = sessionStart ?? samplesToDuration(_framer.samplesFramed);
    _framer.open(start);
    return _framer.add(pcmBytes(samples))..addAll(_framer.close());
  }
}
