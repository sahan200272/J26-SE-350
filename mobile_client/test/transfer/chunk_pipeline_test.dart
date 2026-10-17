import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:echo_vault/transfer/chunk_files.dart';
import 'package:echo_vault/transfer/chunk_pipeline.dart';
import 'package:echo_vault/transfer/sha256.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_opus_encoder.dart';
import '../helpers/session_fixture.dart';
import '../helpers/signals.dart';

const sid = '20261018T100000_a1b2';

void main() {
  late Directory files;
  late FakeOpusEncoder encoder;
  late List<String> published;
  late List<String> logs;
  late SessionFixture f;

  setUp(() {
    files = Directory.systemTemp.createTempSync('echo_vault_files');
    encoder = FakeOpusEncoder();
    published = [];
    logs = [];
    f = SessionFixture()
      ..capture(silence(20) + tone(31) + silence(25) + tone(40) + silence(25))
      ..pause()
      ..resume()
      ..capture(tone(50) + silence(25))
      ..stop();
  });

  tearDown(() => files.deleteSync(recursive: true));

  ChunkPipeline pipeline({int maxAttempts = 2}) => ChunkPipeline(
    sessionId: sid,
    encoder: encoder,
    filesDir: Future.value(files.path),
    appVersion: Future.value('1.0.0+1'),
    maxAttempts: maxAttempts,
    log: logs.add,
    onPublished: published.add,
  );

  /// Queues every segment of the fixture, then finishes.
  Future<Map<String, Object?>> runAll(ChunkPipeline p) {
    for (final s in f.segments) {
      p.add(s, f.runOf(s));
    }
    return p.finish(
      session: f.session,
      segmenter: f.segmenter,
      framer: f.framer,
    );
  }

  Directory outbox() => Directory(OutboxLayout(files.path).sessionDir(sid));
  Map<String, Object?> readJson(String name) =>
      jsonDecode(File('${outbox().path}/$name').readAsStringSync())
          as Map<String, Object?>;

  test('the fixture gives 3 segments', () {
    expect(f.segments, hasLength(3));
  });

  test('write order: each .opus, then its .json, in seq order; the '
      'manifest last; staging left empty', () async {
    await runAll(pipeline());
    expect(published, [
      '${sid}_00000.opus',
      '${sid}_00000.json',
      '${sid}_00001.opus',
      '${sid}_00001.json',
      '${sid}_00002.opus',
      '${sid}_00002.json',
      '${sid}_manifest.json',
    ]);
    final inOutbox = outbox().listSync().map((e) => e.uri.pathSegments.last);
    expect(inOutbox.toSet(), published.toSet());
    expect(
      Directory(OutboxLayout(files.path).stagingDir).listSync(),
      isEmpty,
      reason: 'everything was renamed out of staging',
    );
  });

  test('encodes run one at a time, in seq order, with the queue length '
      'logged; none is skipped', () async {
    final gate = Completer<void>();
    encoder.gates[0] = gate; // hold the first encode while the rest queue
    final p = pipeline();
    for (final s in f.segments) {
      p.add(s, f.runOf(s));
    }
    await encoder.untilCalls(1);
    // Time for a (wrong) second encode to start, if the queue allowed one.
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(p.queueLength, 3);
    expect(encoder.calls, ['${sid}_00000.opus'], reason: 'only one started');
    expect(logs.where((l) => l.startsWith('[encode] queued')), [
      '[encode] queued #0 (queue length 1)',
      '[encode] queued #1 (queue length 2)',
      '[encode] queued #2 (queue length 3)',
    ]);

    gate.complete();
    await p.finish(
      session: f.session,
      segmenter: f.segmenter,
      framer: f.framer,
    );
    expect(encoder.calls, [
      '${sid}_00000.opus',
      '${sid}_00001.opus',
      '${sid}_00002.opus',
    ]);
    expect(encoder.maxConcurrent, 1);
    expect(p.queueLength, 0);
    expect(p.maxQueueLength, 3);
    expect(p.chunks.map((c) => c.seq), [0, 1, 2]);
    expect(logs.where((l) => l.contains('→')).map((l) => l.split(':').first), [
      '[encode] #0 → ${sid}_00000.opus',
      '[encode] #1 → ${sid}_00001.opus',
      '[encode] #2 → ${sid}_00002.opus',
    ]);
    expect(logs.last, contains('3 chunks, 0 failed, max queue length 3'));
  });

  test('segments added while others encode are still all encoded', () async {
    final p = pipeline();
    p.add(f.segments[0], f.runOf(f.segments[0]));
    await encoder.untilCalls(1);
    p.add(f.segments[1], f.runOf(f.segments[1]));
    p.add(f.segments[2], f.runOf(f.segments[2]));
    final m = await p.finish(
      session: f.session,
      segmenter: f.segmenter,
      framer: f.framer,
    );
    expect(m['seqs'], [0, 1, 2]);
  });

  test('sidecar SHA-256 is the hash of the published .opus; the manifest '
      'lists both hashes', () async {
    final m = await runAll(pipeline());
    final chunks = (m['chunks']! as List).cast<Map<String, Object?>>();
    for (final c in chunks) {
      final opus = File('${outbox().path}/${c['audio_file']}')
          .readAsBytesSync();
      final sidecarFile = File('${outbox().path}/${c['sidecar_file']}');
      final sidecar = jsonDecode(sidecarFile.readAsStringSync()) as Map;
      expect(sidecar['sha256'], sha256Hex(opus));
      expect(c['sha256'], sha256Hex(opus));
      expect(c['sidecar_sha256'], sha256Hex(sidecarFile.readAsBytesSync()));
      expect(c['opus_bytes'], opus.length);
      expect(sidecar['encoder'], {
        'name': FakeOpusEncoder.name,
        'bitrate': 32000,
      });
    }
  });

  test('accounting totals in the manifest equal the chunks on disk', () async {
    final m = await runAll(pipeline());
    final sidecars = [
      for (final e in outbox().listSync())
        if (e.path.endsWith('.json') && !e.path.endsWith('_manifest.json'))
          jsonDecode(File(e.path).readAsStringSync()) as Map<String, Object?>,
    ];
    final acc = m['frame_accounting']! as Map<String, Object?>;
    expect(sidecars, hasLength(m['chunk_count']! as int));
    expect(acc['segments_emitted'], sidecars.length);
    expect(
      acc['frames_in_segments'],
      sidecars.fold<int>(0, (sum, s) => sum + (s['frames']! as int)),
    );
    expect(
      acc['samples_in_segments'],
      sidecars.fold<int>(0, (sum, s) => sum + (s['samples']! as int)),
    );
    expect(sidecars.map((s) => s['seq']).toList()..sort(), m['seqs']);
    // The fake encoder stores the sample count it was given.
    for (final s in sidecars) {
      final opus = File('${outbox().path}/${s['audio_file']}')
          .readAsBytesSync();
      final count =
          (opus[4] << 24) | (opus[5] << 16) | (opus[6] << 8) | opus[7];
      expect(count, s['samples']);
    }
    expect(readJson('${sid}_manifest.json'), m);
  });

  test('a failed encode is retried and its partial file removed', () async {
    encoder.failures['${sid}_00001.opus'] = 1;
    final m = await runAll(pipeline());
    expect(m['seqs'], [0, 1, 2]);
    expect(m['failed_chunks'], isEmpty);
    expect(encoder.calls.where((c) => c == '${sid}_00001.opus'), hasLength(2));
    expect(logs, contains(startsWith('[encode] #1 attempt 1 failed')));
    expect(
      File('${outbox().path}/${sid}_00001.opus').lengthSync(),
      greaterThan(3),
      reason: 'the retry wrote the real file',
    );
  });

  test('a chunk that keeps failing is listed in failed_chunks; the others '
      'are still written in order', () async {
    encoder.failures['${sid}_00001.opus'] = 5;
    final m = await runAll(pipeline());
    expect(m['seqs'], [0, 2]);
    expect(m['failed_chunks'], [
      {'seq': 1, 'error': contains('fake encoder failure')},
    ]);
    expect(published, isNot(contains('${sid}_00001.opus')));
    expect(published, isNot(contains('${sid}_00001.json')));
    expect(published.last, '${sid}_manifest.json');
    expect(Directory(OutboxLayout(files.path).stagingDir).listSync(), isEmpty);
  });

  test('a session with no segments still gets a manifest', () async {
    final p = pipeline();
    final m = await p.finish(
      session: f.session,
      segmenter: f.segmenter,
      framer: f.framer,
    );
    expect(m['chunk_count'], 0);
    expect(published, ['${sid}_manifest.json']);
  });

  test('guards: other session, adding after finish, finishing twice', () async {
    final p = pipeline();
    final other = SessionFixture(); // same fixture id, so fake another one
    expect(
      () => ChunkPipeline(
        sessionId: 'other',
        encoder: encoder,
        filesDir: Future.value(files.path),
        appVersion: Future.value('x'),
      ).add(f.segments.first, f.runOf(f.segments.first)),
      throwsArgumentError,
    );
    final first = p.finish(
      session: f.session,
      segmenter: f.segmenter,
      framer: f.framer,
    );
    expect(
      () => p.add(f.segments.first, f.runOf(f.segments.first)),
      throwsStateError,
    );
    final second = p.finish(
      session: other.session,
      segmenter: other.segmenter,
      framer: other.framer,
    );
    expect(await second, await first);
    expect(published, ['${sid}_manifest.json'], reason: 'written once');
  });
}
