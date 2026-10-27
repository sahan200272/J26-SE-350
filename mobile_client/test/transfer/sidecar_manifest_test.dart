import 'dart:convert';

import 'package:echo_vault/encoding/opus_encoder.dart';
import 'package:echo_vault/session/recording_session.dart';
import 'package:echo_vault/transfer/chunk_files.dart';
import 'package:echo_vault/transfer/manifest.dart';
import 'package:echo_vault/transfer/sidecar.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/session_fixture.dart';
import '../helpers/signals.dart';

/// Run 0 with two utterances, a user pause, run 1 with one utterance.
SessionFixture recordedSession() {
  final f = SessionFixture()
    ..capture(silence(20) + tone(31) + silence(25) + tone(40) + silence(25))
    ..pause()
    ..resume()
    ..capture(
      tone(50) + silence(25),
      startup: const Duration(milliseconds: 350),
    )
    ..stop();
  return f;
}

const encoding = OpusEncoding(
  encoderName: 'c2.android.opus.encoder',
  bitrate: 32000,
  inputSamples: 0,
  packets: 42,
  outputBytes: 3456,
);

const timing = ChunkTiming(
  queueWait: Duration(microseconds: 1500),
  encode: Duration(milliseconds: 37),
  queueLengthAtEnqueue: 1,
);

void main() {
  test('chunk and manifest names follow CLAUDE.md', () {
    expect(
      chunkBaseName('20261014T142300_a1b2', 7),
      '20261014T142300_a1b2_00007',
    );
    expect(
      chunkAudioName('20261014T142300_a1b2', 0),
      '20261014T142300_a1b2_00000.opus',
    );
    expect(
      chunkSidecarName('20261014T142300_a1b2', 12345),
      '20261014T142300_a1b2_12345.json',
    );
    expect(
      manifestName('20261014T142300_a1b2'),
      '20261014T142300_a1b2_manifest.json',
    );
    const layout = OutboxLayout('/data/user/0/app/files');
    expect(layout.stagingDir, '/data/user/0/app/files/staging');
    expect(
      layout.sessionDir('20261014T142300_a1b2'),
      '/data/user/0/app/files/outbox/20261014T142300_a1b2',
    );
  });

  group('sidecar (c1-chunk/0.1)', () {
    late SessionFixture f;
    setUp(() => f = recordedSession());

    test('the fixture records 3 segments over 2 runs', () {
      expect(f.segments.map((s) => (s.seq, s.run)), [(0, 0), (1, 0), (2, 1)]);
    });

    test('has exactly the CLAUDE.md fields plus the A4 additions, and no '
        'device identifiers', () {
      final s = f.segments[2];
      final sidecar = chunkSidecar(
        segment: s,
        run: f.runOf(s),
        encoding: encoding,
        sha256: 'ab' * 32,
        appVersion: '1.0.0+1',
        timing: timing,
      );
      expect(sidecar.keys.toSet(), {
        // CLAUDE.md c1-chunk/0.1
        'schema_version', 'session_id', 'seq', 'audio_file', 'codec',
        'sample_rate', 'channels', 'start_ms', 'end_ms', 'start_wallclock',
        'end_wallclock', 'duration_ms', 'vad', 'app_version', 'sha256',
        // A4 additions
        'container', 'run', 'run_tap_offset_ms', 'run_startup_delay_ms',
        'run_capture_start_ms', 'segmenter', 'speech_ratio', 'frames',
        'speech_frames', 'samples', 'audio_start_sample', 'audio_end_sample',
        'forced_split', 'encoder', 'opus_bytes', 'opus_packets', 'processing',
      });
      expect(
        jsonEncode(sidecar).toLowerCase(),
        isNot(matches(RegExp('device|serial|imei|android_id|model|location'))),
      );
    });

    test('values come from the segment, its run and the encoder', () {
      final s = f.segments[2];
      final run = f.runOf(s);
      final j = chunkSidecar(
        segment: s,
        run: run,
        encoding: encoding,
        sha256: 'ab' * 32,
        appVersion: '1.0.0+1',
        timing: timing,
      );
      expect(j['schema_version'], 'c1-chunk/0.1');
      expect(j['session_id'], '20261018T100000_a1b2');
      expect(j['seq'], 2);
      expect(j['audio_file'], '20261018T100000_a1b2_00002.opus');
      expect(j['codec'], 'opus');
      expect(j['container'], 'ogg');
      expect(j['sample_rate'], 16000);
      expect(j['channels'], 1);
      expect(j['start_ms'], s.sessionStart.inMicroseconds / 1000);
      expect(j['end_ms'], s.sessionEnd.inMicroseconds / 1000);
      expect(j['duration_ms'], s.samples.length / 16);
      expect(j['start_wallclock'], startsWith('2026-10-18T10:00:'));
      expect(j['start_wallclock'], matches(RegExp(r'\.\d{3}[+-]\d{2}:\d{2}$')));
      expect(j['vad'], {'type': 'energy', 'config': s.vadConfig});
      expect(j['app_version'], '1.0.0+1');
      expect(j['sha256'], 'ab' * 32);
      expect(j['run'], 1);
      expect(j['run_tap_offset_ms'], run.startOffset.inMicroseconds / 1000);
      expect(j['run_startup_delay_ms'], 350.0);
      expect(
        j['run_capture_start_ms'],
        run.captureStartOffset!.inMicroseconds / 1000,
      );
      expect(j['segmenter'], {'type': 'vad', 'config': s.segmenterConfig});
      expect(j['speech_ratio'], s.speechRatio);
      expect(j['samples'], s.samples.length);
      expect(j['frames'], s.frameCount);
      expect(j['encoder'], {
        'name': 'c2.android.opus.encoder',
        'bitrate': 32000,
      });
      expect(j['opus_bytes'], 3456);
      expect(j['processing'], {
        'queue_wait_ms': 1.5,
        'encode_ms': 37.0,
        'queue_length_at_enqueue': 1,
      });
      // Capture began 350 ms after the tap minus the first chunk (80 ms).
      expect(
        run.captureStartOffset! - run.startOffset,
        const Duration(milliseconds: 270),
      );
    });
  });

  group('manifest', () {
    late SessionFixture f;
    late List<ChunkRecord> records;

    setUp(() {
      f = recordedSession();
      records = [
        for (final s in f.segments.reversed) // out of order on purpose
          ChunkRecord(
            seq: s.seq,
            audioFile: chunkAudioName(s.sessionId!, s.seq),
            sidecarFile: chunkSidecarName(s.sessionId!, s.seq),
            sha256: '${s.seq}' * 64,
            sidecarSha256: 'f' * 64,
            opusBytes: 1000 + s.seq,
            run: s.run,
            start: s.sessionStart,
            end: s.sessionEnd,
            samples: s.samples.length,
            frames: s.frameCount,
            encoderName: 'c2.android.opus.encoder',
            bitrate: 32000,
          ),
      ];
    });

    Map<String, Object?> manifest({List<FailedChunk> failed = const []}) =>
        sessionManifest(
          session: f.session,
          segmenter: f.segmenter,
          framer: f.framer,
          chunks: records,
          failedChunks: failed,
          appVersion: '1.0.0+1',
          encoderBitrate: 32000,
          maxQueueLength: 2,
        );

    test('session start/end, chunk list with SHA-256, seqs in order', () {
      final m = manifest();
      expect(m['schema_version'], 'c1-manifest/0.1');
      expect(m['session_id'], '20261018T100000_a1b2');
      expect(m['app_version'], '1.0.0+1');
      expect(
        m['session_start_wallclock'],
        '2026-10-18T10:00:00.000${_offset()}',
      );
      final end = f.session.stoppedOffset!;
      expect(m['session_end_ms'], end.inMicroseconds / 1000);
      expect(
        m['session_end_wallclock'],
        startsWith(
          '2026-10-18T10:00:${(end.inMilliseconds ~/ 1000).toString().padLeft(2, '0')}',
        ),
      );
      expect(m['chunk_count'], 3);
      expect(m['seqs'], [0, 1, 2]);
      final chunks = (m['chunks']! as List).cast<Map<String, Object?>>();
      expect(chunks.map((c) => c['seq']), [0, 1, 2]);
      expect(chunks.first['sha256'], '0' * 64);
      expect(chunks.first['audio_file'], '20261018T100000_a1b2_00000.opus');
      expect(chunks.first['sidecar_file'], '20261018T100000_a1b2_00000.json');
      expect(m['encoder'], {
        'name': 'c2.android.opus.encoder',
        'bitrate': 32000,
      });
      expect(m['encode_queue'], {'max_length': 2});
      expect(m['failed_chunks'], isEmpty);
    });

    test('pause intervals with reasons, and every run', () {
      final m = manifest();
      final pause = f.session.pauseIntervals.single;
      expect(m['pause_intervals'], [
        {
          'start_ms': pause.start.inMicroseconds / 1000,
          'end_ms': pause.end!.inMicroseconds / 1000,
          'reason': 'user',
        },
      ]);
      final runs = (m['runs']! as List).cast<Map<String, Object?>>();
      expect(runs.map((r) => r['index']), [0, 1]);
      expect(runs.map((r) => r['startup_delay_ms']), [400.0, 350.0]);
      expect(runs[1]['tap_offset_ms'], pause.end!.inMicroseconds / 1000);
    });

    test('frame-accounting totals equal the chunk contents', () {
      final m = manifest();
      final acc = m['frame_accounting']! as Map<String, Object?>;
      final chunks = (m['chunks']! as List).cast<Map<String, Object?>>();
      expect(acc['balanced'], isTrue);
      expect(acc['segments_emitted'], m['chunk_count']);
      expect(
        acc['frames_in_segments'],
        chunks.fold<int>(0, (sum, c) => sum + (c['frames']! as int)),
      );
      expect(
        acc['samples_in_segments'],
        chunks.fold<int>(0, (sum, c) => sum + (c['samples']! as int)),
      );
      expect(
        (acc['frames_in_segments']! as int) +
            (acc['frames_in_discarded_segments']! as int) +
            (acc['frames_excluded']! as int),
        acc['frames_seen'],
      );
      expect(acc['frames_seen'], f.framer.framesEmitted);
      expect((m['capture']! as Map)['frames_emitted'], f.framer.framesEmitted);
    });

    test('a failed chunk is listed and missing from seqs', () {
      records.removeWhere((r) => r.seq == 1);
      final m = manifest(failed: [const FailedChunk(1, 'boom')]);
      expect(m['seqs'], [0, 2]);
      expect(m['failed_chunks'], [
        {'seq': 1, 'error': 'boom'},
      ]);
    });

    test('auto_background pauses keep their reason', () {
      final g = SessionFixture()
        ..capture(tone(40) + silence(25))
        ..pause(PauseReason.autoBackground)
        ..resume()
        ..capture(tone(40) + silence(25))
        ..stop();
      final m = sessionManifest(
        session: g.session,
        segmenter: g.segmenter,
        framer: g.framer,
        chunks: const [],
        failedChunks: const [],
        appVersion: 'x',
        encoderBitrate: 32000,
        maxQueueLength: 0,
      );
      expect(
        (m['pause_intervals']! as List).single,
        containsPair('reason', 'auto_background'),
      );
      expect((m['encoder']! as Map)['name'], isNull, reason: 'no chunks');
    });
  });
}

String _offset() {
  final o = DateTime(2026, 10, 18, 10).timeZoneOffset;
  final m = o.inMinutes.abs();
  return '${o.isNegative ? '-' : '+'}${(m ~/ 60).toString().padLeft(2, '0')}:'
      '${(m % 60).toString().padLeft(2, '0')}';
}
