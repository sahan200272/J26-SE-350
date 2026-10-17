import 'dart:math';
import 'dart:typed_data';

import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/pcm.dart';

/// Feeds [bytes] to [framer] in chunks of the given sizes (cycled), and
/// returns every frame produced.
List<PcmFrame> feedInChunks(
  PcmFramer framer,
  Uint8List bytes,
  List<int> chunkSizes,
) {
  final frames = <PcmFrame>[];
  var pos = 0;
  var k = 0;
  while (pos < bytes.length) {
    final size = min(chunkSizes[k++ % chunkSizes.length], bytes.length - pos);
    frames.addAll(framer.add(Uint8List.sublistView(bytes, pos, pos + size)));
    pos += size;
  }
  return frames;
}

/// The real samples of [frames], concatenated.
List<int> validSamples(Iterable<PcmFrame> frames) => [
  for (final f in frames) ...f.samples.take(f.validSamples),
];

const ms = Duration(milliseconds: 1);

void main() {
  test('frame size is 512 samples = 32 ms at 16 kHz', () {
    expect(kFrameSamples, 512);
    expect(samplesToDuration(kFrameSamples), const Duration(milliseconds: 32));
    expect(samplesToDuration(1), const Duration(microseconds: 62));
    expect(samplesToDuration(16000), const Duration(seconds: 1));
  });

  group('odd chunk sizes, exact sample accounting', () {
    const totalSamples = 5000; // 9 full frames + 392
    final source = rampSamples(totalSamples);
    final bytes = pcmBytes(source);

    final chunkPatterns = <String, List<int>>{
      'one byte at a time': [1],
      'three bytes': [3],
      'odd mix incl. 0': [1, 0, 7, 1023, 2, 5, 1],
      'frame size + 1 byte': [1025],
      'frame size - 1 byte': [1023],
      'whole buffer at once': [bytes.length],
      'Android-like 2560 B': [2560],
    };

    for (final MapEntry(key: name, value: sizes) in chunkPatterns.entries) {
      test(name, () {
        final framer = PcmFramer()..open(Duration.zero);
        final frames = feedInChunks(framer, bytes, sizes)
          ..addAll(framer.close());

        // No sample lost, duplicated or reordered.
        expect(validSamples(frames), source);
        expect(framer.samplesFramed, totalSamples);
        expect(framer.bytesAccepted, bytes.length);
        expect(framer.droppedBytes, 0);
        expect(framer.discardedOddBytes, 0);

        // 9 full frames, then one padded frame from close().
        expect(frames, hasLength(10));
        expect(frames.take(9).every((f) => f.validSamples == 512), isTrue);
        expect(frames.last.validSamples, 392);
        expect(frames.last.isPadded, isTrue);
        expect(framer.paddedFrames, 1);
        expect(frames.last.samples.skip(392), everyElement(0));

        for (var i = 0; i < frames.length; i++) {
          final f = frames[i];
          expect(f.index, i);
          expect(f.samples, hasLength(512));
          expect(f.audioOffsetSamples, i * 512);
          expect(f.sessionOffset, ms * (32 * i));
        }
      });
    }

    test('a sample split across chunks keeps its sign', () {
      final framer = PcmFramer()..open(Duration.zero);
      // -2 = 0xFFFE → bytes FE FF; 0x1234 → 34 12.
      expect(framer.add(Uint8List.fromList([0xFE])), isEmpty);
      expect(framer.add(Uint8List.fromList([0xFF, 0x34])), isEmpty);
      expect(framer.add(Uint8List.fromList([0x12])), isEmpty);
      final frames = framer.close();
      expect(validSamples(frames), [-2, 0x1234]);
      expect(framer.bytesAccepted, 4);
    });

    test('extremes: -32768 and 32767 survive framing', () {
      final framer = PcmFramer()..open(Duration.zero);
      final frames = framer.add(pcmBytes([-32768, 32767, 0, -1]))
        ..addAll(framer.close());
      expect(validSamples(frames), [-32768, 32767, 0, -1]);
    });

    test('a run ending on half a sample: byte discarded and counted', () {
      final framer = PcmFramer()..open(Duration.zero);
      framer.add(Uint8List.fromList([1, 0, 2, 0, 3])); // 2.5 samples
      final frames = framer.close();
      expect(validSamples(frames), [1, 2]);
      expect(framer.discardedOddBytes, 1);
      expect(
        framer.bytesAccepted,
        2 * framer.samplesFramed + framer.discardedOddBytes,
      );

      // The stray byte must not be glued onto the next run's first byte.
      framer.open(const Duration(seconds: 1));
      final next = framer.add(pcmBytes([7, 8]))..addAll(framer.close());
      expect(validSamples(next), [7, 8]);
    });

    test('random chunking: accepted bytes = 2 × framed samples', () {
      final rng = Random(42);
      final framer = PcmFramer()..open(Duration.zero);
      final source = rampSamples(48000, start: 123); // 3 s
      final frames = <PcmFrame>[];
      final bytes = pcmBytes(source);
      var pos = 0;
      while (pos < bytes.length) {
        final size = min(rng.nextInt(3000), bytes.length - pos);
        frames.addAll(
          framer.add(Uint8List.sublistView(bytes, pos, pos + size)),
        );
        pos += size;
      }
      frames.addAll(framer.close());
      expect(validSamples(frames), source);
      expect(framer.bytesAccepted, 2 * framer.samplesFramed);
      expect(frames.length, (48000 / 512).ceil());
    });

    test('frames do not share sample buffers', () {
      final framer = PcmFramer()..open(Duration.zero);
      final frames = framer.add(pcmBytes(rampSamples(1024)));
      expect(frames, hasLength(2));
      expect(identical(frames[0].samples, frames[1].samples), isFalse);
      final copy = Int16List.fromList(frames[0].samples);
      framer.add(pcmBytes(rampSamples(512, start: 9999)));
      expect(frames[0].samples, copy);
    });
  });

  group('FR2: nothing is framed while closed (paused/stopped)', () {
    test('zero frames emitted while paused; bytes dropped and counted', () {
      final drops = <int>[];
      final framer = PcmFramer(onDrop: (bytes, _) => drops.add(bytes));
      framer.open(Duration.zero);
      expect(framer.add(pcmBytes(rampSamples(600))), hasLength(1));
      framer.close(); // pause: flushes the 88-sample tail
      final framedBeforePause = framer.framesEmitted;

      // Bytes still arriving while paused, in several odd-sized chunks.
      var droppedFrames = 0;
      for (final size in [1, 1024, 3, 5000, 2048]) {
        droppedFrames += framer.add(Uint8List(size)).length;
      }

      expect(droppedFrames, 0);
      expect(framer.framesEmitted, framedBeforePause);
      expect(framer.droppedBytes, 1 + 1024 + 3 + 5000 + 2048);
      expect(framer.droppedChunks, 5);
      expect(drops, [1, 1024, 3, 5000, 2048]);
      expect(framer.samplesFramed, 600, reason: 'dropped bytes never count');
    });

    test('before the first open and after the final close', () {
      final framer = PcmFramer();
      expect(framer.add(constantPcm(2048)), isEmpty);
      framer
        ..open(Duration.zero)
        ..add(constantPcm(512))
        ..close();
      expect(framer.add(constantPcm(4096)), isEmpty);
      expect(framer.framesEmitted, 1);
      expect(framer.droppedBytes, 4096 + 8192);
      expect(framer.droppedChunks, 2);
    });

    test('a partial frame is flushed at pause, not carried across it', () {
      final framer = PcmFramer()..open(Duration.zero);
      framer.add(pcmBytes(rampSamples(700)));
      final flushed = framer.close();
      expect(flushed.single.validSamples, 188);
      expect(flushed.single.run, 0);

      framer.open(const Duration(seconds: 10));
      final after = framer.add(pcmBytes(rampSamples(512, start: 700)));
      expect(after.single.run, 1);
      expect(after.single.validSamples, 512);
      expect(after.single.sessionOffset, const Duration(seconds: 10));
    });

    test('the caller can set the run index (skipped runs); it must grow', () {
      final framer = PcmFramer()..open(Duration.zero);
      framer.close();
      // Session run 1 never received capture; the next capture is run 2.
      framer.open(const Duration(seconds: 3), run: 2);
      final frames = framer.add(constantPcm(512));
      expect(frames.single.run, 2);
      expect(framer.runCount, 2, reason: 'runs opened');
      framer.close();
      expect(() => framer.open(Duration.zero, run: 2), throwsArgumentError);
      expect(framer.isOpen, isFalse);
    });

    test('close is a no-op when already closed; open twice throws', () {
      final framer = PcmFramer();
      expect(framer.close(), isEmpty);
      framer.open(Duration.zero);
      expect(() => framer.open(Duration.zero), throwsStateError);
      framer.close();
      expect(framer.close(), isEmpty);
      expect(framer.isOpen, isFalse);
    });
  });

  anchoringTests();

  group('timeline offsets across pause/resume', () {
    test('audioOffset counts samples; sessionOffset = resume offset + '
        'samples since resume', () {
      final framer = PcmFramer()..open(Duration.zero);

      // Run 0: 1000 samples (62.5 ms), session offsets 0..
      final run0 = framer.add(pcmBytes(rampSamples(1000)))
        ..addAll(framer.close()); // paused at, say, 2.000 s on the clock

      // Run 1 starts when resumed at session offset 5.0 s.
      framer.open(const Duration(seconds: 5));
      final run1 = framer.add(pcmBytes(rampSamples(1100, start: 1000)))
        ..addAll(framer.close());

      // Run 2 resumed at 9.25 s.
      framer.open(const Duration(milliseconds: 9250));
      final run2 = framer.add(pcmBytes(rampSamples(512, start: 2100)))
        ..addAll(framer.close());

      expect(run0.map((f) => (f.run, f.validSamples)), [(0, 512), (0, 488)]);
      expect(run0.map((f) => f.audioOffsetSamples), [0, 512]);
      expect(run0.map((f) => f.sessionOffset), [Duration.zero, ms * 32]);

      expect(run1.map((f) => (f.run, f.validSamples)), [
        (1, 512),
        (1, 512),
        (1, 76),
      ]);
      expect(run1.map((f) => f.audioOffsetSamples), [1000, 1512, 2024]);
      expect(run1.map((f) => f.sessionOffset), [
        const Duration(seconds: 5),
        const Duration(milliseconds: 5032),
        const Duration(milliseconds: 5064),
      ]);
      // 1000 samples = 62.5 ms of audio before run 1.
      expect(run1.first.audioOffset, const Duration(microseconds: 62500));

      expect(run2.single.run, 2);
      expect(run2.single.audioOffsetSamples, 2100);
      expect(run2.single.sessionOffset, const Duration(milliseconds: 9250));
      expect(run2.single.isPadded, isFalse);

      expect(framer.runCount, 3);
      expect(framer.samplesFramed, 2612);
      expect(
        [...run0, ...run1, ...run2].map((f) => f.index),
        List.generate(6, (i) => i),
      );
    });

    test('sessionOffset is exact (no drift) over a long run', () {
      final framer = PcmFramer()..open(const Duration(milliseconds: 1500));
      final frames = framer.add(Uint8List(16000 * 60 * 2)); // 60 s
      expect(frames, hasLength(1875));
      expect(
        frames.last.sessionOffset,
        const Duration(milliseconds: 1500 + 1874 * 32),
      );
      expect(frames.last.audioOffset, const Duration(milliseconds: 1874 * 32));
    });
  });
}

void anchoringTests() {
  group('runs anchored at the first chunk (live capture)', () {
    test('run start = arrival of the first chunk − its duration', () {
      final framer = PcmFramer()
        ..openAtFirstChunk(run: 0, notBefore: Duration.zero);
      expect(framer.awaitingAnchor, isTrue);
      expect(framer.runStartOffset, isNull);

      // 1280 samples (80 ms) arrive 700 ms after the session started.
      final frames = framer.add(
        pcmBytes(rampSamples(1280)),
        arrivedAt: const Duration(milliseconds: 700),
      );
      expect(framer.awaitingAnchor, isFalse);
      expect(framer.runStartOffset, const Duration(milliseconds: 620));
      expect(frames.map((f) => f.sessionOffset), [
        const Duration(milliseconds: 620),
        const Duration(milliseconds: 652),
      ]);
      // Later chunks do not move the anchor.
      final more = framer.add(
        pcmBytes(rampSamples(256)),
        arrivedAt: const Duration(seconds: 99),
      );
      expect(more.single.sessionOffset, const Duration(milliseconds: 684));
      expect(framer.clampedAnchors, 0);
    });

    test('never before the tap: an early estimate is raised and counted', () {
      final framer = PcmFramer()
        ..openAtFirstChunk(run: 1, notBefore: const Duration(seconds: 5));
      final frames = framer.add(
        pcmBytes(rampSamples(1280)),
        arrivedAt: const Duration(milliseconds: 5030), // 30 ms < 80 ms
      );
      expect(framer.runStartOffset, const Duration(seconds: 5));
      expect(frames.first.sessionOffset, const Duration(seconds: 5));
      expect(frames.first.run, 1);
      expect(framer.clampedAnchors, 1);
    });

    test(
      'empty chunks do not anchor; the first real chunk needs arrivedAt',
      () {
        final framer = PcmFramer()..openAtFirstChunk();
        expect(framer.add(Uint8List(0)), isEmpty);
        expect(framer.awaitingAnchor, isTrue);
        expect(() => framer.add(pcmBytes([1, 2])), throwsArgumentError);
      },
    );

    test('an odd first chunk counts its whole samples only', () {
      final framer = PcmFramer()..openAtFirstChunk();
      framer.add(
        Uint8List(1025), // 512 samples + half
        arrivedAt: const Duration(milliseconds: 100),
      );
      expect(framer.runStartOffset, const Duration(milliseconds: 68));
    });

    test('a run that closes before its first chunk keeps no anchor', () {
      final framer = PcmFramer()..openAtFirstChunk();
      expect(framer.close(), isEmpty);
      expect(framer.awaitingAnchor, isFalse);
      framer.openAtFirstChunk(run: 1, notBefore: const Duration(seconds: 2));
      framer.add(
        pcmBytes(rampSamples(512)),
        arrivedAt: const Duration(seconds: 3),
      );
      expect(framer.runStartOffset, const Duration(milliseconds: 2968));
      expect(framer.currentRun, 1);
    });
  });
}
