import 'dart:math';

import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/segmentation/segment.dart';
import 'package:echo_vault/segmentation/segmenter.dart';
import 'package:echo_vault/vad/energy_vad.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/signals.dart';

const ms = Duration(milliseconds: 1);

/// Runs [segmenter] over [runs] (each a list of frames), ending every run.
List<Segment> segment(Segmenter segmenter, List<List<PcmFrame>> runs) => [
  for (final run in runs) ...[
    for (final f in run) ...segmenter.add(f),
    ...segmenter.endRun(),
  ],
];

VadSegmenter defaultSegmenter() => VadSegmenter(EnergyVad());

/// Frame index range [start, end) of a segment, in 512-sample frames.
(int, int) frameRange(Segment s) =>
    (s.audioStartSample ~/ 512, (s.audioEndSample + 511) ~/ 512);

void expectBalanced(Segmenter s, int totalFrames) {
  final st = s.stats;
  expect(st.framesPending, 0);
  expect(st.framesSeen, totalFrames);
  expect(
    st.framesInSegments + st.framesInDiscardedSegments + st.framesExcluded,
    totalFrames,
    reason: 'NFR7 accounting',
  );
  expect(st.isBalanced, isTrue);
}

void main() {
  test('silence only: no segments, every frame excluded', () {
    final s = defaultSegmenter();
    expect(segment(s, [FrameSource().run(silence(200))]), isEmpty);
    expect(s.stats.framesExcluded, 200);
    expectBalanced(s, 200);
  });

  group('onset and offset timing (defaults: onset 3, hangover 19, '
      'pre-roll 10, post-roll 8)', () {
    test('one burst: starts 10 frames before the burst, ends 8 after', () {
      final s = defaultSegmenter();
      final segs = segment(s, [
        FrameSource().run(silence(40) + tone(30) + silence(40)),
      ]);
      expect(segs, hasLength(1));
      expect(frameRange(segs.single), (30, 78));
      expect(segs.single.sessionStart, ms * (30 * 32));
      expect(segs.single.sessionEnd, ms * (78 * 32));
      expect(segs.single.speechFrameCount, 30);
      expect(segs.single.frameCount, 48);
      expect(segs.single.speechRatio, closeTo(30 / 48, 1e-9));
      expect(segs.single.forcedSplit, isFalse);
      expectBalanced(s, 110);
    });

    test('the segment is emitted when the hangover completes, not before', () {
      final s = defaultSegmenter();
      final frames = FrameSource().run(silence(40) + tone(30) + silence(40));
      final emittedAt = <int>[];
      for (var i = 0; i < frames.length; i++) {
        if (s.add(frames[i]).isNotEmpty) emittedAt.add(i);
        if (i == 41) expect(s.inSpeech, isFalse, reason: 'onset needs 3');
        if (i == 42) expect(s.inSpeech, isTrue);
      }
      // Last speech frame 69; the 19th silence frame is frame 88.
      expect(emittedAt, [88]);
    });

    test('onset needs consecutive speech frames', () {
      final pattern = <int>[];
      for (var i = 0; i < 20; i++) {
        pattern.addAll(silence(2) + tone(2)); // never 3 in a row
      }
      final s = defaultSegmenter();
      expect(segment(s, [FrameSource().run(silence(20) + pattern)]), isEmpty);
      expect(s.stats.excludedSpeechFrames, 40);
      expectBalanced(s, 100);
    });

    test('a gap shorter than the hangover keeps one segment; one as long '
        'splits it', () {
      final short = defaultSegmenter();
      expect(
        segment(short, [
          FrameSource().run(
            silence(20) + tone(20) + silence(18) + tone(20) + silence(30),
          ),
        ]),
        hasLength(1),
      );
      final long = defaultSegmenter();
      final segs = segment(long, [
        FrameSource().run(
          silence(20) + tone(20) + silence(19) + tone(20) + silence(30),
        ),
      ]);
      expect(segs, hasLength(2));
      // First ends at 40 + 8; the second's pre-roll reaches back only to
      // frames the first did not take (49..58), so they never overlap.
      expect(frameRange(segs[0]), (10, 48));
      expect(frameRange(segs[1]), (49, 87));
      expect(segs.map((s) => s.seq), [0, 1]);
    });

    test('pre-roll at the start of a run uses only the frames it has', () {
      final s = defaultSegmenter();
      final segs = segment(s, [FrameSource().run(silence(3) + tone(20))]);
      expect(frameRange(segs.single), (0, 23));
    });

    test('post-roll is cut short by the end of the run', () {
      final s = defaultSegmenter();
      final segs = segment(s, [
        FrameSource().run(silence(20) + tone(20) + silence(3)),
      ]);
      expect(frameRange(segs.single), (10, 43));
      expectBalanced(s, 43);
    });
  });

  group('minimum length', () {
    test('a 5-frame (160 ms) burst is discarded and counted', () {
      final s = defaultSegmenter();
      final segs = segment(s, [
        FrameSource().run(silence(20) + tone(5) + silence(40)),
      ]);
      expect(segs, isEmpty);
      expect(s.stats.segmentsDiscarded, 1);
      expect(s.stats.framesInDiscardedSegments, 10 + 5 + 8);
      expectBalanced(s, 65);
    });

    test('7 frames (224 ms) is kept; seq only counts kept segments', () {
      final s = defaultSegmenter();
      final segs = segment(s, [
        FrameSource().run(
          silence(20) + tone(5) + silence(30) + tone(7) + silence(30),
        ),
      ]);
      expect(segs.single.seq, 0);
      expect(s.stats.segmentsDiscarded, 1);
      expect(s.stats.segmentsEmitted, 1);
    });
  });

  group('maximum length 30 s', () {
    test('65 s of speech is split at the limit with no gap or overlap', () {
      final s = defaultSegmenter();
      final frames = FrameSource().run(
        silence(5) + speechLike(2031) + silence(30),
      );
      final segs = segment(s, [frames]);
      expect(segs.map((x) => x.forcedSplit), [true, true, false]);
      for (final seg in segs) {
        expect(seg.duration, lessThanOrEqualTo(const Duration(seconds: 30)));
      }
      // 937 frames = 29.984 s is the most that fits in 30 s.
      expect(segs[0].frameCount, 937);
      expect(segs[1].frameCount, 937);
      expect(segs[1].audioStartSample, segs[0].audioEndSample);
      expect(segs[2].audioStartSample, segs[1].audioEndSample);
      expect(s.stats.forcedSplits, 2);
      expectBalanced(s, frames.length);
    });

    test('a short tail after a forced split is kept (not "too short")', () {
      final s = defaultSegmenter();
      // 937 frames fill the first segment; 3 more frames of speech remain.
      final segs = segment(s, [
        FrameSource().run(speechLike(940) + silence(30)),
      ]);
      expect(segs, hasLength(2));
      expect(segs.last.speechFrameCount, 3);
      expect(s.stats.segmentsDiscarded, 0);
    });
  });

  group('pauses and run boundaries', () {
    test('speech running into a pause ends there; the next run starts a new '
        'segment', () {
      final source = FrameSource();
      final run0 = source.run(silence(10) + tone(40));
      final run1 = source.run(
        tone(40) + silence(30),
        sessionStart: const Duration(seconds: 20),
      );
      final s = defaultSegmenter();
      final segs = segment(s, [run0, run1]);
      expect(segs, hasLength(2));
      expect(segs.map((x) => x.run), [0, 1]);
      expect(segs[0].audioEndSample, 50 * 512, reason: 'ends at the pause');
      expect(segs[1].audioStartSample, 50 * 512, reason: 'no pre-roll yet');
      expect(segs[1].sessionStart, const Duration(seconds: 20));
      expectBalanced(s, 120);
    });

    test('a frame of a new run ends the previous run even without endRun', () {
      final source = FrameSource();
      final run0 = source.run(tone(40));
      final run1 = source.run(tone(40) + silence(30));
      final s = defaultSegmenter();
      final segs = [
        for (final f in [...run0, ...run1]) ...s.add(f),
        ...s.endRun(),
      ];
      expect(segs.map((x) => x.run), [0, 1]);
    });

    test('no segment ever spans two runs (random speech, many pauses)', () {
      final rng = Random(7);
      final source = FrameSource();
      final runs = <List<PcmFrame>>[];
      for (var r = 0; r < 6; r++) {
        final samples = <int>[];
        for (var k = 0; k < 8; k++) {
          samples.addAll(
            rng.nextBool()
                ? tone(1 + rng.nextInt(60))
                : silence(1 + rng.nextInt(40)),
          );
        }
        runs.add(source.run(samples, sessionStart: Duration(seconds: 100 * r)));
      }
      final s = defaultSegmenter();
      final segs = segment(s, runs);
      expect(segs, isNotEmpty);
      for (final seg in segs) {
        final run = runs[seg.run];
        expect(
          seg.audioStartSample,
          greaterThanOrEqualTo(run.first.audioOffsetSamples),
        );
        expect(
          seg.audioEndSample,
          lessThanOrEqualTo(
            run.last.audioOffsetSamples + run.last.validSamples,
          ),
        );
      }
    });
  });

  group('NFR7 accounting identity', () {
    for (final seed in [1, 2, 3, 4, 5]) {
      test('random signal, seed $seed', () {
        final rng = Random(seed);
        final source = FrameSource();
        final runs = <List<PcmFrame>>[];
        for (var r = 0; r < 1 + rng.nextInt(4); r++) {
          final samples = <int>[];
          for (var k = 0; k < 20; k++) {
            final n = 1 + rng.nextInt(50);
            samples.addAll(switch (rng.nextInt(3)) {
              0 => tone(n, amplitude: 500 + rng.nextInt(8000)),
              1 => noise(n, dbfs: -65 + rng.nextInt(10).toDouble(), seed: k),
              _ => silence(n),
            });
          }
          // An odd sample count makes the run end with a padded frame.
          samples.addAll(List.filled(rng.nextInt(511), 2000));
          runs.add(source.run(samples));
        }
        final total = runs.fold(0, (sum, r) => sum + r.length);
        final s = defaultSegmenter();
        final segs = segment(s, runs);
        expectBalanced(s, total);
        expect(
          segs.fold(0, (sum, x) => sum + x.frameCount),
          s.stats.framesInSegments,
        );
        expect(
          segs.fold(0, (sum, x) => sum + x.samples.length),
          s.stats.samplesInSegments,
        );
        // Segments are disjoint and in order.
        for (var i = 1; i < segs.length; i++) {
          expect(
            segs[i].audioStartSample,
            greaterThanOrEqualTo(segs[i - 1].audioEndSample),
          );
        }
      });
    }

    test('stats count pending frames while a segment is open', () {
      final s = defaultSegmenter();
      for (final f in FrameSource().run(silence(20) + tone(10))) {
        s.add(f);
      }
      expect(s.stats.framesPending, greaterThan(0));
      expect(s.stats.isBalanced, isTrue);
      s.endRun();
      expect(s.stats.framesPending, 0);
    });
  });

  test('noise plus bursts: one segment per burst', () {
    final bg = noise(400, dbfs: -60, seed: 9);
    final bursts = <int>[];
    for (var i = 0; i < 4; i++) {
      bursts.addAll(silence(50) + tone(30, amplitude: 2000));
    }
    bursts.addAll(silence(80));
    final s = defaultSegmenter();
    final segs = segment(s, [FrameSource().run(mix(bg, bursts))]);
    expect(segs, hasLength(4));
    for (var i = 0; i < 4; i++) {
      final burstStart = 50 + i * 80;
      final (start, end) = frameRange(segs[i]);
      expect(start, burstStart - 10);
      expect(end, burstStart + 30 + 8);
    }
  });

  test('segment samples are the frames\' real samples, padding excluded', () {
    final samples = silence(10) + tone(20) + List.filled(100, 1234);
    final s = defaultSegmenter();
    final seg = segment(s, [FrameSource().run(samples)]).single;
    expect(seg.samples.toList(), samples.sublist(0, 30 * 512 + 100));
    expect(seg.audioEndSample, 30 * 512 + 100);
    expect(seg.sessionEnd, samplesToDuration(30 * 512 + 100));
  });

  test('session id, wall clock and metadata', () {
    final wall = DateTime(2026, 10, 15, 14, 0, 0);
    final s = VadSegmenter.forSession(
      EnergyVad(),
      const VadSegmenterConfig(),
      sessionId: '20261015T140000_beef',
      sessionStartWallClock: wall,
    );
    final seg = segment(s, [
      FrameSource().run(
        silence(40) + tone(30) + silence(40),
        sessionStart: const Duration(seconds: 2),
      ),
    ]).single;
    expect(seg.sessionId, '20261015T140000_beef');
    expect(seg.sessionStart, const Duration(milliseconds: 2960));
    expect(seg.startWallClock, wall.add(const Duration(milliseconds: 2960)));
    expect(seg.endWallClock, wall.add(seg.sessionEnd));
    final json = seg.toJson();
    expect(json['vad'], {'type': 'energy', 'config': EnergyVad().config});
    expect(json['segmenter'], {
      'type': 'vad',
      'config': const VadSegmenterConfig().toJson(),
    });
    expect(json['start_ms'], 2960.0);
    expect(json['start_wallclock'], startsWith('2026-10-15T14:00:02.960'));
    expect(json['speech_ratio'], closeTo(30 / 48, 1e-9));
    expect(json.containsKey('samples'), isTrue);
    expect(json['samples'], seg.samples.length, reason: 'count, not data');
  });

  test('config JSON round trip and equality', () {
    const c = VadSegmenterConfig(
      onsetFrames: 2,
      hangoverFrames: 25,
      preRollFrames: 5,
      postRollFrames: 25,
      minSpeechMs: 0,
      maxSegmentMs: 10000,
    );
    expect(VadSegmenterConfig.fromJson(c.toJson()), c);
    expect(
      VadSegmenterConfig.fromJson(const VadSegmenterConfig().toJson()),
      const VadSegmenterConfig(),
    );
    expect(c, isNot(const VadSegmenterConfig()));
    expect(
      () => VadSegmenterConfig(postRollFrames: 20, hangoverFrames: 19),
      throwsA(isA<AssertionError>()),
    );
  });
}
