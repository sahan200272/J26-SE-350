import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/segmentation/segment.dart';
import 'package:echo_vault/segmentation/segmenter.dart';
import 'package:echo_vault/vad/energy_vad.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/signals.dart';

List<Segment> segment(Segmenter segmenter, List<List<PcmFrame>> runs) => [
  for (final run in runs) ...[
    for (final f in run) ...segmenter.add(f),
    ...segmenter.endRun(),
  ],
];

void main() {
  test('5 s windows are 156 frames (4.992 s)', () {
    expect(const FixedChunkConfig().windowFrames, 156);
    expect(const FixedChunkConfig(windowMs: 1000).windowFrames, 31);
  });

  test('continuous speech: back-to-back windows; the run tail is a shorter '
      'window judged the same way', () {
    final s = FixedChunkSegmenter(EnergyVad());
    final segs = segment(s, [FrameSource().run(speechLike(400))]);
    expect(segs.map((x) => x.frameCount), [156, 156, 88]);
    expect(segs[1].audioStartSample, segs[0].audioEndSample);
    expect(segs.every((x) => x.speechRatio > 0.8), isTrue);
    expect(segs.map((x) => x.seq), [0, 1, 2]);
    expect(s.stats.framesInSegments, 400);
    expect(s.stats.isBalanced, isTrue);
  });

  test('windows below the speech-ratio threshold are excluded', () {
    final s = FixedChunkSegmenter(EnergyVad()); // threshold 0.1
    final segs = segment(s, [
      FrameSource().run(
        // Window 1: 16/156 speech (10.3 %) → kept.
        silence(70) +
            tone(16) +
            silence(70) +
            // Window 2: 15/156 (9.6 %) → excluded.
            silence(70) +
            tone(15) +
            silence(71) +
            // Window 3: no speech → excluded.
            silence(156),
      ),
    ]);
    expect(segs, hasLength(1));
    expect(segs.single.speechFrameCount, 16);
    expect(segs.single.speechRatio, closeTo(16 / 156, 1e-9));
    final st = s.stats;
    expect(st.framesInSegments, 156);
    expect(st.framesExcluded, 312);
    expect(st.excludedSpeechFrames, 15);
    expect(st.framesInDiscardedSegments, 0);
    expect(st.isBalanced, isTrue);
    expect(st.framesSeen, 468);
  });

  test('windows never cross a pause', () {
    final source = FrameSource();
    final s = FixedChunkSegmenter(EnergyVad());
    final segs = segment(s, [
      source.run(speechLike(100)),
      source.run(speechLike(100), sessionStart: const Duration(seconds: 30)),
    ]);
    expect(segs.map((x) => (x.run, x.frameCount)), [(0, 100), (1, 100)]);
    expect(segs[1].sessionStart, const Duration(seconds: 30));
  });

  test('segment metadata names the baseline', () {
    final s = FixedChunkSegmenter(EnergyVad());
    final seg = segment(s, [FrameSource().run(tone(10))]).single;
    expect(seg.segmenterType, 'fixed');
    expect(seg.segmenterConfig, {'window_ms': 5000, 'min_speech_ratio': 0.1});
    expect(seg.vadType, 'energy');
  });

  test('config JSON round trip and equality', () {
    const c = FixedChunkConfig(windowMs: 3000, minSpeechRatio: 0.25);
    expect(FixedChunkConfig.fromJson(c.toJson()), c);
    expect(c, isNot(const FixedChunkConfig()));
  });
}
