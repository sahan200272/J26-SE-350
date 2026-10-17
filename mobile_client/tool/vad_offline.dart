// Offline VAD segmentation of a 16 kHz mono 16-bit WAV, using the same
// framer, VAD and segmenter code as the app (pure Dart, no Flutter).
//
//   dart run tool/vad_offline.dart <input.wav> [options]
//
// Options (defaults are the app's):
//   --segmenter vad|fixed        proposed VAD segmentation or Table 5 baseline
//   --vad energy                 VAD implementation (only `energy` so far)
//   --out <file.json>            write the JSON report there
//   --run-starts <s0,s1,...>     audio sample offsets where recording runs
//                                begin (default 0); segments never cross them
//   --frames true                also list every frame's level and decision
//   EnergyVad:     --margin-db --absolute-min-dbfs --noise-window-ms
//                  --initial-floor-dbfs <dBFS|none>
//   VadSegmenter:  --onset-frames --hangover-frames --pre-roll-frames
//                  --post-roll-frames --min-speech-ms --max-segment-ms
//   FixedChunk:    --window-ms --min-speech-ratio
import 'dart:convert';
import 'dart:io';

import 'package:echo_vault/segmentation/offline_segmentation.dart';
import 'package:echo_vault/segmentation/segmenter.dart';
import 'package:echo_vault/vad/energy_vad.dart';

void main(List<String> args) {
  try {
    exitCode = _run(args);
  } on FormatException catch (e) {
    stderr.writeln('error: ${e.message}');
    exitCode = 64;
  } on ArgumentError catch (e) {
    stderr.writeln('error: $e');
    exitCode = 64;
  }
}

int _run(List<String> args) {
  final positional = <String>[];
  final opts = <String, String>{};
  for (var i = 0; i < args.length; i++) {
    final a = args[i];
    if (a.startsWith('--')) {
      if (i + 1 >= args.length) throw FormatException('$a needs a value');
      opts[a.substring(2)] = args[++i];
    } else {
      positional.add(a);
    }
  }
  if (positional.length != 1) {
    stderr.writeln(
      'usage: dart run tool/vad_offline.dart <input.wav> '
      '[--segmenter vad|fixed] [--out file.json] [options]',
    );
    return 64;
  }
  final known = {
    'segmenter', 'vad', 'out', 'run-starts', 'frames', //
    'margin-db', 'absolute-min-dbfs', 'noise-window-ms', 'initial-floor-dbfs',
    'onset-frames', 'hangover-frames', 'pre-roll-frames', 'post-roll-frames',
    'min-speech-ms', 'max-segment-ms', 'window-ms', 'min-speech-ratio',
  };
  final unknown = opts.keys.where((k) => !known.contains(k));
  if (unknown.isNotEmpty) {
    throw FormatException('unknown option --${unknown.first}');
  }

  double? d(String k) => opts[k] == null ? null : double.parse(opts[k]!);
  int? n(String k) => opts[k] == null ? null : int.parse(opts[k]!);

  if ((opts['vad'] ?? 'energy') != 'energy') {
    throw FormatException('unknown VAD "${opts['vad']}" (only "energy")');
  }
  const v = EnergyVadConfig();
  final floor = opts['initial-floor-dbfs'];
  final vad = EnergyVad(
    EnergyVadConfig(
      marginDb: d('margin-db') ?? v.marginDb,
      absoluteMinDbfs: d('absolute-min-dbfs') ?? v.absoluteMinDbfs,
      noiseWindowMs: n('noise-window-ms') ?? v.noiseWindowMs,
      initialNoiseFloorDbfs: floor == null
          ? v.initialNoiseFloorDbfs
          : (floor == 'none' ? null : double.parse(floor)),
    ),
  );

  final Segmenter segmenter;
  switch (opts['segmenter'] ?? 'vad') {
    case 'vad':
      const c = VadSegmenterConfig();
      segmenter = VadSegmenter(
        vad,
        VadSegmenterConfig(
          onsetFrames: n('onset-frames') ?? c.onsetFrames,
          hangoverFrames: n('hangover-frames') ?? c.hangoverFrames,
          preRollFrames: n('pre-roll-frames') ?? c.preRollFrames,
          postRollFrames: n('post-roll-frames') ?? c.postRollFrames,
          minSpeechMs: n('min-speech-ms') ?? c.minSpeechMs,
          maxSegmentMs: n('max-segment-ms') ?? c.maxSegmentMs,
        ),
      );
    case 'fixed':
      const c = FixedChunkConfig();
      segmenter = FixedChunkSegmenter(
        vad,
        FixedChunkConfig(
          windowMs: n('window-ms') ?? c.windowMs,
          minSpeechRatio: d('min-speech-ratio') ?? c.minSpeechRatio,
        ),
      );
    case final other:
      throw FormatException('unknown segmenter "$other" (vad or fixed)');
  }

  final input = positional.single;
  final runStarts = opts['run-starts'] == null
      ? const [0]
      : [for (final s in opts['run-starts']!.split(',')) int.parse(s.trim())];
  final result = segmentWav(
    File(input).readAsBytesSync(),
    segmenter,
    runStartSamples: runStarts,
  );
  final report = offlineReport(
    result,
    segmenter,
    input: input,
    includeFrames: opts['frames'] == 'true',
  );
  final json = const JsonEncoder.withIndent('  ').convert(report);
  if (opts['out'] case final out?) {
    File(out).writeAsStringSync('$json\n');
    stdout.writeln('wrote $out');
  } else {
    stdout.writeln(json);
  }

  final summary = report['summary']! as Map<String, Object?>;
  stdout.writeln(
    '${segmenter.type} segmenter, ${vad.type} VAD: '
    '${result.segments.length} segments, '
    '${(summary['seconds_in_segments']! as double).toStringAsFixed(2)} s of '
    '${(report['duration_s']! as double).toStringAsFixed(2)} s kept; '
    'frames ${result.stats.framesSeen} = '
    '${result.stats.framesInSegments} in segments + '
    '${result.stats.framesInDiscardedSegments} in discarded + '
    '${result.stats.framesExcluded} excluded '
    '(${result.stats.isBalanced ? 'balanced' : 'NOT BALANCED'})',
  );
  for (final seg in result.segments) {
    stdout.writeln(
      '  #${seg.seq} run ${seg.run}: '
      '${(seg.sessionStart.inMicroseconds / 1e6).toStringAsFixed(3)}–'
      '${(seg.sessionEnd.inMicroseconds / 1e6).toStringAsFixed(3)} s, '
      'speech ratio ${seg.speechRatio.toStringAsFixed(2)}'
      '${seg.forcedSplit ? ' (forced split)' : ''}',
    );
  }
  return result.stats.isBalanced ? 0 : 1;
}
