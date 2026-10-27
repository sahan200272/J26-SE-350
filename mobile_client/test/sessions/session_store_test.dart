import 'dart:convert';
import 'dart:io';

import 'package:echo_vault/sessions/session_store.dart';
import 'package:echo_vault/sessions/session_titles.dart';
import 'package:flutter_test/flutter_test.dart';

/// Records calls; fails [protect] when [failWith] is set.
class FakeGuard implements RemoteCopyGuard {
  final calls = <String>[];
  Object? failWith;

  /// Whether the session folder still existed when [protect] ran.
  bool? existedAtProtect;
  String? filesDir;

  @override
  Future<void> protect(String sessionId) async {
    calls.add('protect:$sessionId');
    if (filesDir != null) {
      existedAtProtect = Directory('$filesDir/outbox/$sessionId').existsSync();
    }
    if (failWith case final e?) throw e;
  }

  @override
  Future<void> afterDelete(String sessionId) async {
    calls.add('after:$sessionId');
  }
}

void main() {
  late Directory files;

  setUp(() async {
    files = await Directory.systemTemp.createTemp('session_store_test');
  });

  tearDown(() async {
    if (await files.exists()) await files.delete(recursive: true);
  });

  Future<Directory> sessionDir(String id) =>
      Directory('${files.path}/outbox/$id').create(recursive: true);

  Future<void> writeJson(Directory dir, String name, Object json) =>
      File('${dir.path}/$name').writeAsString(jsonEncode(json));

  OutboxSessionStore store() => OutboxSessionStore(Future.value(files.path));

  test('no outbox: empty list', () async {
    expect(await store().list(), isEmpty);
  });

  test('complete session: read from its manifest', () async {
    const id = '20261018T013925_2fc3';
    final dir = await sessionDir(id);
    await writeJson(dir, '${id}_manifest.json', {
      'schema_version': 'c1-manifest/0.1',
      'session_id': id,
      'session_start_wallclock': '2026-10-18T01:39:25.729+05:30',
      'session_end_wallclock': '2026-10-18T01:40:01.086+05:30',
      'session_end_ms': 35356.259,
      'recorded_ms': 28843.316,
      'chunk_count': 2,
      'chunks': [
        {'seq': 1, 'start_ms': 2763.85, 'end_ms': 6475.85, 'opus_bytes': 200},
        {'seq': 0, 'start_ms': 587.85, 'end_ms': 1771.85, 'opus_bytes': 100},
      ],
      'failed_chunks': <Object>[],
      'pause_intervals': [
        {'start_ms': 10000.0, 'end_ms': 12000.0, 'reason': 'user'},
      ],
      'vad': {'type': 'energy', 'config': <String, Object>{}},
      'encoder': {'name': 'c2.android.opus.encoder', 'bitrate': 32000},
    });

    final sessions = await store().list();
    expect(sessions, hasLength(1));
    final s = sessions.single;
    expect(s.id, id);
    expect(s.complete, isTrue);
    expect(s.error, isNull);
    expect([for (final c in s.chunks) c.seq], [0, 1], reason: 'sorted');
    expect(s.chunkCount, 2);
    expect(s.recordedMs, closeTo(28843.316, 1e-6));
    expect(s.timelineMs, closeTo(35356.259, 1e-6));
    expect(s.speechMs, closeTo(1184 + 3712, 1e-6));
    expect(s.opusBytes, 300);
    expect(s.pauseCount, 1);
    expect(s.vadType, 'energy');
    expect(s.encoderBitrate, 32000);
    expect(
      s.start!.toUtc(),
      DateTime.utc(2026, 10, 17, 20, 9, 25, 729),
      reason: 'offset +05:30 respected',
    );
  });

  test('no manifest yet: chunks from the sidecars, marked incomplete', () async {
    const id = '20261019T090000_beef';
    final dir = await sessionDir(id);
    await writeJson(dir, '${id}_00000.json', {
      'seq': 0,
      'start_ms': 100.0,
      'end_ms': 1100.0,
      'opus_bytes': 512,
      'vad': {'type': 'energy'},
    });
    await File('${dir.path}/${id}_00000.opus').writeAsBytes([0, 1, 2]);

    final s = (await store().list()).single;
    expect(s.complete, isFalse);
    expect(s.chunkCount, 1);
    expect(s.chunks.single.durationMs, 1000);
    expect(s.vadType, 'energy');
    expect(s.start, DateTime(2026, 10, 19, 9));
    expect(s.timelineMs, 1100);
  });

  test('unreadable manifest: listed with an error, not thrown', () async {
    const id = '20261019T100000_dead';
    final dir = await sessionDir(id);
    await File('${dir.path}/${id}_manifest.json').writeAsString('{not json');

    final s = (await store().list()).single;
    expect(s.error, isNotNull);
    expect(s.complete, isFalse);
    expect(s.start, DateTime(2026, 10, 19, 10));
  });

  test('newest first', () async {
    await sessionDir('20261018T010000_aaaa');
    await sessionDir('20261019T010000_bbbb');
    await sessionDir('20261017T010000_cccc');
    expect([for (final s in await store().list()) s.id], [
      '20261019T010000_bbbb',
      '20261018T010000_aaaa',
      '20261017T010000_cccc',
    ]);
  });

  test('startFromSessionId', () {
    expect(
      startFromSessionId('20261014T142300_a1b2'),
      DateTime(2026, 10, 14, 14, 23),
    );
    expect(startFromSessionId('not-a-session'), isNull);
  });

  group('titles', () {
    test('normalizeSessionTitle trims, collapses whitespace, caps length', () {
      expect(normalizeSessionTitle('  Team   sync \n notes  '), 'Team sync notes');
      expect(normalizeSessionTitle('   '), isNull);
      expect(normalizeSessionTitle(''), isNull);
      expect(normalizeSessionTitle('a\u0007b'), 'ab');
      final long = 'x' * 100;
      expect(normalizeSessionTitle(long)!.length, kMaxSessionTitleLength);
    });

    test('rename persists and survives a new store (app restart)', () async {
      const id = '20261018T013925_2fc3';
      await sessionDir(id);
      await store().rename(id, '  Project   kickoff ');

      final reopened = OutboxSessionStore(Future.value(files.path));
      final s = (await reopened.list()).single;
      expect(s.title, 'Project kickoff');
      // Session files are untouched; the title lives in prefs/.
      expect(
        File('${files.path}/prefs/session_titles.json').existsSync(),
        isTrue,
      );
      expect(Directory('${files.path}/outbox/$id').listSync(), isEmpty);
    });

    test('rename rejects an empty title and an unknown session', () async {
      const id = '20261018T013925_2fc3';
      await sessionDir(id);
      await expectLater(
        store().rename(id, '   '),
        throwsA(isA<SessionActionException>()),
      );
      await expectLater(
        store().rename('20261018T013925_ffff', 'Name'),
        throwsA(isA<SessionActionException>()),
      );
      expect((await store().list()).single.title, isNull);
    });

    test('unreadable titles file falls back to automatic titles', () async {
      const id = '20261018T013925_2fc3';
      await sessionDir(id);
      await Directory('${files.path}/prefs').create();
      await File('${files.path}/prefs/session_titles.json').writeAsString('{');
      expect((await store().list()).single.title, isNull);
    });
  });

  group('delete', () {
    const keep = '20261017T090000_aaaa';
    const gone = '20261018T013925_2fc3';
    late FakeGuard guard;

    OutboxSessionStore guarded({DateTime Function()? now}) =>
        OutboxSessionStore(
          Future.value(files.path),
          guard: guard,
          now: now ?? () => DateTime.now().add(const Duration(hours: 1)),
        );

    setUp(() async {
      guard = FakeGuard()..filesDir = files.path;
      for (final id in [keep, gone]) {
        final dir = await sessionDir(id);
        await writeJson(dir, '${id}_manifest.json', {'chunks': <Object>[]});
        await File('${dir.path}/${id}_00000.opus').writeAsBytes([1, 2, 3]);
      }
      await Directory('${files.path}/staging').create();
      await File('${files.path}/staging/${gone}_00001.opus').writeAsBytes([1]);
      await File('${files.path}/staging/${keep}_00001.opus').writeAsBytes([1]);
      await File('${files.path}/outbox/.stignore').writeAsString('/staging\n');
      await Directory('${files.path}/outbox/.stfolder').create();
    });

    test('protects the PC copy first, then deletes only that session', () async {
      await guarded().rename(gone, 'To delete');
      await guarded().rename(keep, 'Keep me');

      await guarded().delete(gone);

      expect(guard.calls, ['protect:$gone', 'after:$gone']);
      expect(guard.existedAtProtect, isTrue, reason: 'protect runs first');
      expect(Directory('${files.path}/outbox/$gone').existsSync(), isFalse);
      expect(Directory('${files.path}/outbox/$keep').existsSync(), isTrue);
      expect(File('${files.path}/outbox/.stignore').existsSync(), isTrue);
      expect(Directory('${files.path}/outbox/.stfolder').existsSync(), isTrue);
      expect(
        File('${files.path}/staging/${gone}_00001.opus').existsSync(),
        isFalse,
      );
      expect(
        File('${files.path}/staging/${keep}_00001.opus').existsSync(),
        isTrue,
      );
      final left = await guarded().list();
      expect([for (final s in left) s.id], [keep]);
      expect(left.single.title, 'Keep me');
      expect((await SessionTitleStore(Future.value(files.path)).load()), {
        keep: 'Keep me',
      });
    });

    test('guard failure: nothing is deleted', () async {
      guard.failWith = Exception('Syncthing busy');
      await expectLater(
        guarded().delete(gone),
        throwsA(isA<SessionActionException>()),
      );
      expect(Directory('${files.path}/outbox/$gone').existsSync(), isTrue);
    });

    test('no guard: deletion refused, nothing deleted', () async {
      await expectLater(
        store().delete(gone),
        throwsA(isA<SessionActionException>()),
      );
      expect(Directory('${files.path}/outbox/$gone').existsSync(), isTrue);
    });

    test('a session that may still be saving is not deleted', () async {
      const fresh = '20261019T100000_beef';
      final dir = await sessionDir(fresh);
      await File('${dir.path}/${fresh}_00000.opus').writeAsBytes([1]);
      await expectLater(
        guarded(now: DateTime.now).delete(fresh),
        throwsA(isA<SessionActionException>()),
      );
      expect(dir.existsSync(), isTrue);
      expect(guard.calls, isEmpty);
    });

    test('invalid or missing IDs are rejected', () async {
      await expectLater(guarded().delete('..'), throwsArgumentError);
      await expectLater(guarded().delete('.stfolder'), throwsArgumentError);
      await expectLater(
        guarded().delete('20261018T013925_ffff'),
        throwsA(isA<SessionActionException>()),
      );
      expect(Directory('${files.path}/outbox/$keep').existsSync(), isTrue);
    });
  });

  test('non-session folders (.stfolder) are not listed', () async {
    await Directory('${files.path}/outbox/.stfolder').create(recursive: true);
    await sessionDir('20261018T010000_aaaa');
    expect([for (final s in await store().list()) s.id], [
      '20261018T010000_aaaa',
    ]);
  });
}
