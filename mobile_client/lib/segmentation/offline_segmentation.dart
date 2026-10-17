import 'dart:math' as math;
import 'dart:typed_data';

import '../capture/audio_capture.dart';
import '../capture/level_meter.dart';
import '../capture/pcm_framer.dart';
import '../capture/wav_reader.dart';
import 'segment.dart';
import 'segmenter.dart';

/// Result of segmenting a WAV file offline.
class OfflineSegmentation {
  const OfflineSegmentation({
    required this.segments,
    required this.stats,
    required this.totalSamples,
    required this.runStartSamples,
    required this.frameLevelsDbfs,
    required this.frameRuns,
    required this.frameSpeech,
    required this.frameScores,
  });

  final List<Segment> segments;
  final SegmenterStats stats;
  final int totalSamples;
  final List<int> runStartSamples;

  /// RMS level of every frame (real samples only), in order.
  final List<double> frameLevelsDbfs;

  /// Run, VAD decision and VAD score of every frame, in order.
  final List<int> frameRuns;
  final List<bool> frameSpeech;
  final List<double> frameScores;
}

/// Runs [segmenter] over a 16 kHz mono 16-bit WAV exactly as the app does
/// live: the same framer (fed in [chunkBytes] chunks, 2560 B like the
/// Galaxy A06), VAD and segmenter code. Pure Dart.
///
/// A WAV does not record pauses. [runStartSamples] (ascending, starting at
/// 0) marks where recording runs begin on the audio timeline; each run is
/// framed and segmented separately and anchored at its audio offset, so
/// session offsets equal audio offsets.
OfflineSegmentation segmentWav(
  Uint8List wavBytes,
  Segmenter segmenter, {
  List<int> runStartSamples = const [0],
  int chunkBytes = 2560,
}) {
  final wav = readWav(wavBytes);
  if (wav.sampleRate != kSampleRate ||
      wav.channels != kChannels ||
      wav.bitsPerSample != 16) {
    throw FormatException(
      'Expected 16 kHz mono 16-bit PCM, got ${wav.sampleRate} Hz, '
      '${wav.channels} ch, ${wav.bitsPerSample}-bit.',
    );
  }
  final total = wav.sampleCount;
  if (runStartSamples.isEmpty ||
      runStartSamples.first != 0 ||
      runStartSamples.any((s) => s < 0 || s > total)) {
    throw ArgumentError.value(runStartSamples, 'runStartSamples');
  }
  for (var i = 1; i < runStartSamples.length; i++) {
    if (runStartSamples[i] <= runStartSamples[i - 1]) {
      throw ArgumentError.value(
        runStartSamples,
        'runStartSamples',
        'must be strictly increasing',
      );
    }
  }

  final framer = PcmFramer();
  final segments = <Segment>[];
  final levels = <double>[];
  final runs = <int>[];
  final speech = <bool>[];
  final scores = <double>[];
  void take(List<PcmFrame> frames) {
    for (final f in frames) {
      levels.add(rmsDbfs(f.samples, f.validSamples));
      runs.add(f.run);
      segments.addAll(segmenter.add(f));
      final d = segmenter.lastDecision!;
      speech.add(d.isSpeech);
      scores.add(d.score);
    }
  }

  for (var r = 0; r < runStartSamples.length; r++) {
    final startByte = runStartSamples[r] * 2;
    final endByte = r + 1 < runStartSamples.length
        ? runStartSamples[r + 1] * 2
        : total * 2;
    framer.open(samplesToDuration(runStartSamples[r]), run: r);
    for (var pos = startByte; pos < endByte; pos += chunkBytes) {
      final end = math.min(pos + chunkBytes, endByte);
      take(framer.add(Uint8List.sublistView(wav.data, pos, end)));
    }
    take(framer.close());
    segments.addAll(segmenter.endRun());
  }

  return OfflineSegmentation(
    segments: segments,
    stats: segmenter.stats,
    totalSamples: total,
    runStartSamples: List.unmodifiable(runStartSamples),
    frameLevelsDbfs: levels,
    frameRuns: runs,
    frameSpeech: speech,
    frameScores: scores,
  );
}

/// Nearest-rank percentile of [values] (0 < p ≤ 100).
double percentile(List<double> values, double p) {
  if (values.isEmpty) throw ArgumentError('no values');
  final sorted = List.of(values)..sort();
  final rank = (p / 100 * sorted.length).ceil().clamp(1, sorted.length);
  return sorted[rank - 1];
}

/// JSON report: segments (with start/end in seconds), configs and summary;
/// with [includeFrames], also every frame's level and VAD decision.
Map<String, Object?> offlineReport(
  OfflineSegmentation result,
  Segmenter segmenter, {
  String? input,
  bool includeFrames = false,
}) {
  double s(Duration d) => d.inMicroseconds / 1e6;
  final levels = result.frameLevelsDbfs;
  final speechSeconds = result.segments.fold(
    0.0,
    (sum, seg) => sum + s(seg.duration),
  );
  return {
    'input': input,
    'sample_rate': kSampleRate,
    'channels': kChannels,
    'duration_s': s(samplesToDuration(result.totalSamples)),
    'run_start_samples': result.runStartSamples,
    'segmenter': {'type': segmenter.type, 'config': segmenter.config},
    'vad': {'type': segmenter.vad.type, 'config': segmenter.vad.config},
    'segments': [
      for (final seg in result.segments)
        {
          'start_s': s(seg.sessionStart),
          'end_s': s(seg.sessionEnd),
          ...seg.toJson(),
        },
    ],
    'summary': {
      'segments': result.segments.length,
      'seconds_in_segments': speechSeconds,
      'fraction_in_segments': result.totalSamples == 0
          ? 0
          : result.stats.samplesInSegments / result.totalSamples,
      if (levels.isNotEmpty)
        'frame_level_dbfs_percentiles': {
          for (final p in [5, 10, 25, 50, 75, 90, 95, 99])
            'p$p': double.parse(
              percentile(levels, p.toDouble()).toStringAsFixed(2),
            ),
        },
      ...result.stats.toJson(),
    },
    if (includeFrames)
      'frames': [
        for (var i = 0; i < levels.length; i++)
          {
            'index': i,
            'run': result.frameRuns[i],
            'level_dbfs': double.parse(levels[i].toStringAsFixed(2)),
            'speech': result.frameSpeech[i],
            'score': double.parse(result.frameScores[i].toStringAsFixed(2)),
          },
      ],
  };
}
