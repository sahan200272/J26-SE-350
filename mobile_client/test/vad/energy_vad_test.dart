import 'dart:typed_data';

import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/vad/energy_vad.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/signals.dart';

/// Classifies every frame of [samples] (one run) with [vad].
List<bool> decide(EnergyVad vad, List<int> samples) => [
  for (final f in FrameSource().run(samples)) vad.classify(f).isSpeech,
];

void main() {
  test('digital silence is never speech; score is level − threshold', () {
    final vad = EnergyVad();
    final frames = FrameSource().run(silence(50));
    for (final f in frames) {
      final d = vad.classify(f);
      expect(d.isSpeech, isFalse);
      // floor −96 → threshold = max(−84, −50) = −50; level −96.
      expect(d.score, closeTo(-46, 1e-9));
    }
    expect(vad.lastThresholdDbfs, -50);
  });

  test('a tone burst after silence is speech, and only the burst', () {
    final vad = EnergyVad();
    final d = decide(vad, silence(20) + tone(10) + silence(20));
    expect(d.sublist(0, 20), everyElement(isFalse));
    expect(d.sublist(20, 30), everyElement(isTrue));
    expect(d.sublist(30), everyElement(isFalse));
  });

  test('speech bursts over steady −60 dBFS noise', () {
    final vad = EnergyVad();
    final bg = noise(150, dbfs: -60);
    final burst = silence(50) + tone(25, amplitude: 1500) + silence(75);
    final d = decide(vad, mix(bg, burst)); // burst ≈ −29.8 dBFS
    expect(d.sublist(0, 50).where((s) => s), isEmpty);
    expect(d.sublist(50, 75), everyElement(isTrue));
    expect(d.sublist(75).where((s) => s), isEmpty);
    expect(vad.lastNoiseFloorDbfs, closeTo(-60, 1.5));
  });

  group('adaptive noise floor', () {
    test('a loud steady background (−45 dBFS) stops counting as speech '
        'within the noise window, while bursts above it still do', () {
      final vad = EnergyVad(); // window 3000 ms = 94 frames
      final bg = noise(300, dbfs: -45, seed: 2);
      final bursts = silence(200) + tone(30, amplitude: 8000) + silence(70);
      final d = decide(vad, mix(bg, bursts));
      // Seeded at −60 → threshold −48 for the first window: noise is speech.
      expect(d.sublist(0, 50), everyElement(isTrue));
      // After the window the floor is the noise itself: not speech.
      expect(d.sublist(100, 200).where((s) => s), isEmpty);
      expect(d.sublist(200, 230), everyElement(isTrue)); // ≈ −15 dBFS
      expect(vad.lastNoiseFloorDbfs, closeTo(-45, 2));
    });

    test('a background step from −60 to −40 dBFS is learned within the '
        'window; a drop is followed at once', () {
      final vad = EnergyVad();
      final d = decide(
        vad,
        noise(200, dbfs: -60, seed: 3) +
            noise(300, dbfs: -40, seed: 4) +
            noise(100, dbfs: -60, seed: 5),
      );
      expect(d.sublist(0, 200).where((s) => s), isEmpty);
      expect(d.sublist(200, 220), everyElement(isTrue), reason: 'not yet');
      expect(d.sublist(300, 500).where((s) => s), isEmpty, reason: 'learned');
      expect(d.sublist(500).where((s) => s), isEmpty, reason: 'drop');
    });

    test('a perfectly steady sound longer than the window becomes '
        'background (like a fan); speech-like dips keep the floor low', () {
      final steady = decide(EnergyVad(), silence(10) + tone(300));
      expect(steady.sublist(10, 100), everyElement(isTrue));
      expect(steady.sublist(110).where((s) => s), isEmpty);

      final speech = decide(EnergyVad(), silence(10) + speechLike(300));
      final toneFrames = [
        for (var f = 0; f < 300; f++)
          if (f % 12 < 10) speech[10 + f],
      ];
      expect(toneFrames, everyElement(isTrue));
    });

    test('without a seed the floor starts at the first frame', () {
      final vad = EnergyVad(const EnergyVadConfig(initialNoiseFloorDbfs: null));
      final d = decide(vad, noise(10, dbfs: -45) + tone(5, amplitude: 8000));
      expect(d.sublist(0, 10).where((s) => s), isEmpty);
      expect(d.sublist(10), everyElement(isTrue));
    });
  });

  test('the absolute minimum applies whatever the floor', () {
    final vad = EnergyVad();
    // After digital silence the floor is −96; −55 dBFS (amplitude 81 → RMS
    // ≈ −55.1) stays below the −50 dBFS minimum, −45 does not.
    final d = decide(
      vad,
      silence(20) + tone(10, amplitude: 81) + tone(10, amplitude: 260),
    );
    expect(d.sublist(20, 30), everyElement(isFalse));
    expect(d.sublist(30, 40), everyElement(isTrue));
  });

  test('padded frames are measured on their valid samples only', () {
    final vad = EnergyVad();
    for (final f in FrameSource().run(silence(10))) {
      vad.classify(f);
    }
    final samples = Int16List(kFrameSamples)..fillRange(0, 64, 3277);
    final padded = PcmFrame(
      index: 10,
      run: 0,
      samples: samples,
      validSamples: 64,
      audioOffsetSamples: 5120,
      sessionOffset: const Duration(milliseconds: 320),
    );
    final d = vad.classify(padded);
    expect(vad.lastLevelDbfs, closeTo(-20, 0.01), reason: 'not diluted');
    expect(d.isSpeech, isTrue);
  });

  test('reset forgets the floor', () {
    final vad = EnergyVad();
    decide(vad, noise(200, dbfs: -45));
    expect(vad.lastNoiseFloorDbfs, greaterThan(-50));
    vad.reset();
    expect(vad.lastNoiseFloorDbfs, isNull);
    final d = decide(vad, noise(10, dbfs: -45));
    expect(d, everyElement(isTrue), reason: 'seed −60 again');
  });

  group('config', () {
    test('JSON round trip, equality and copyWith', () {
      const c = EnergyVadConfig(
        marginDb: 9.5,
        absoluteMinDbfs: -52,
        noiseWindowMs: 1500,
        initialNoiseFloorDbfs: null,
      );
      expect(EnergyVadConfig.fromJson(c.toJson()), c);
      expect(
        EnergyVadConfig.fromJson(const EnergyVadConfig().toJson()),
        const EnergyVadConfig(),
      );
      expect(c.copyWith(marginDb: 12).marginDb, 12);
      expect(
        c.copyWith(initialNoiseFloorDbfs: (value: -70)).initialNoiseFloorDbfs,
        -70,
      );
      expect(c, isNot(const EnergyVadConfig()));
    });

    test('defaults and type as written to segment metadata', () {
      final vad = EnergyVad();
      expect(vad.type, 'energy');
      expect(vad.config, {
        'margin_db': 12.0,
        'absolute_min_dbfs': -50.0,
        'noise_window_ms': 3000,
        'initial_noise_floor_dbfs': -60.0,
      });
      expect(const EnergyVadConfig().noiseWindowFrames, 94);
    });
  });
}
