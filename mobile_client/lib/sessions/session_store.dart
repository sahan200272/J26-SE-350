/// The sessions on this phone, built from the files the transfer layer
/// already writes to `files/outbox/<session_id>/` (the session manifest and
/// the chunk sidecars), plus user-chosen titles kept in app-private
/// `files/prefs/session_titles.json` (never synced).
///
/// Writes: [OutboxSessionStore.rename] (titles file only) and
/// [OutboxSessionStore.delete] (one session folder, after the
/// [RemoteCopyGuard] has made sure the deletion will not reach the PC).
///
/// Pure Dart (dart:io), no Flutter imports.
library;

import 'dart:convert';
import 'dart:io';

import 'session_titles.dart';

/// A session folder name, e.g. `20261014T142300_a1b2` (see session_id.dart).
/// Anything else in the outbox (`.stfolder`, `.stignore`, …) is not a session.
final sessionIdPattern = RegExp(r'^\d{8}T\d{6}_[0-9a-f]{4}$');

bool isSessionId(String id) => sessionIdPattern.hasMatch(id);

/// One speech chunk of a session (session-relative offsets).
class ChunkSummary {
  const ChunkSummary({
    required this.seq,
    required this.startMs,
    required this.endMs,
    this.opusBytes,
  });

  final int seq;
  final double startMs;
  final double endMs;
  final int? opusBytes;

  double get durationMs => endMs - startMs;
}

/// One session folder in the outbox.
class SessionSummary {
  const SessionSummary({
    required this.id,
    required this.complete,
    required this.chunks,
    this.start,
    this.end,
    this.sessionEndMs,
    this.recordedMs,
    this.failedChunks = 0,
    this.pauseCount = 0,
    this.vadType,
    this.encoderBitrate,
    this.error,
    this.title,
  });

  final String id;

  /// Title the user gave the recording; null for the automatic title.
  final String? title;

  /// The session manifest (written on Stop, after the last chunk) exists.
  final bool complete;
  final List<ChunkSummary> chunks;

  /// Local wall-clock start/end, from the manifest (or the session ID).
  final DateTime? start;
  final DateTime? end;

  /// Session length including pauses, from the manifest.
  final double? sessionEndMs;

  /// Recorded time excluding pauses, from the manifest.
  final double? recordedMs;
  final int failedChunks;
  final int pauseCount;
  final String? vadType;
  final int? encoderBitrate;

  /// Why the folder could not be read completely, if it could not.
  final String? error;

  int get chunkCount => chunks.length;

  /// Total detected speech kept as chunks.
  double get speechMs => chunks.fold<double>(0, (sum, c) => sum + c.durationMs);

  int get opusBytes => chunks.fold<int>(0, (sum, c) => sum + (c.opusBytes ?? 0));

  /// A copy with [title] replaced (null: automatic title).
  SessionSummary withTitle(String? title) => SessionSummary(
    id: id,
    complete: complete,
    chunks: chunks,
    start: start,
    end: end,
    sessionEndMs: sessionEndMs,
    recordedMs: recordedMs,
    failedChunks: failedChunks,
    pauseCount: pauseCount,
    vadType: vadType,
    encoderBitrate: encoderBitrate,
    error: error,
    title: title,
  );

  /// Timeline length for drawing: manifest length, else the last chunk end.
  double get timelineMs =>
      sessionEndMs ??
      chunks.fold<double>(0, (m, c) => c.endMs > m ? c.endMs : m);
}

/// Where the sessions list comes from (a fake in widget tests).
abstract interface class SessionSource {
  /// Every session, newest first.
  Future<List<SessionSummary>> list();

  /// Gives session [id] the title [title] (already validated with
  /// [normalizeSessionTitle]). Throws if it cannot be saved.
  Future<void> rename(String id, String title);

  /// Deletes session [id] from this phone. Throws, without deleting
  /// anything, if the deletion cannot be done safely.
  Future<void> delete(String id);
}

/// Thrown when a session cannot be renamed or deleted; [message] is shown to
/// the user.
class SessionActionException implements Exception {
  const SessionActionException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Makes sure deleting a session on the phone does not delete the PC's copy.
///
/// The outbox is a send-only Syncthing folder and the PC's is receive-only,
/// so a plain local deletion would be sent to the PC. [protect] must make
/// Syncthing ignore the session folder before it is deleted; it throws if it
/// cannot. [afterDelete] runs once the folder is gone.
abstract interface class RemoteCopyGuard {
  Future<void> protect(String sessionId);
  Future<void> afterDelete(String sessionId);
}

/// Lists and reads session folders under `<filesDir>/outbox/`.
class OutboxSessionStore implements SessionSource {
  OutboxSessionStore(
    this._filesDir, {
    SessionTitleStore? titles,
    this.guard,
    DateTime Function()? now,
  }) : titles = titles ?? SessionTitleStore(_filesDir),
       _now = now ?? DateTime.now;

  final Future<String> _filesDir;
  final SessionTitleStore titles;

  /// Required for [delete]; without it deletion is refused.
  final RemoteCopyGuard? guard;
  final DateTime Function() _now;

  /// An unfinished session whose files changed this recently may still be
  /// being written (the save after Stop), so it is not deleted yet.
  static const busyWindow = Duration(seconds: 30);

  Future<Directory> _outbox() async => Directory('${await _filesDir}/outbox');

  /// Every session folder, newest first. Empty if there is no outbox yet.
  @override
  Future<List<SessionSummary>> list() async {
    final outbox = await _outbox();
    if (!await outbox.exists()) return const [];
    final names = await titles.load();
    final sessions = <SessionSummary>[];
    await for (final entity in outbox.list(followLinks: false)) {
      if (entity is! Directory) continue;
      final id = entity.uri.pathSegments.where((s) => s.isNotEmpty).last;
      if (!isSessionId(id)) continue;
      final session = await readSession(entity, id);
      sessions.add(names[id] == null ? session : session.withTitle(names[id]));
    }
    // Session IDs start with the local start time, so they sort by time.
    sessions.sort((a, b) => b.id.compareTo(a.id));
    return sessions;
  }

  @override
  Future<void> rename(String id, String title) async {
    if (!isSessionId(id)) throw ArgumentError.value(id, 'id');
    final normalized = normalizeSessionTitle(title);
    if (normalized == null) {
      throw const SessionActionException('Enter a name for the recording.');
    }
    final dir = Directory('${(await _outbox()).path}/$id');
    if (!await dir.exists()) {
      throw const SessionActionException(
        'This recording is no longer on this phone.',
      );
    }
    try {
      await titles.setTitle(id, normalized);
    } catch (_) {
      throw const SessionActionException(
        'The new name could not be saved. Try again.',
      );
    }
  }

  @override
  Future<void> delete(String id) async {
    // Only ever a single, well-formed session folder inside the outbox.
    if (!isSessionId(id)) throw ArgumentError.value(id, 'id');
    final filesDir = await _filesDir;
    final dir = Directory('$filesDir/outbox/$id');
    if (!await dir.exists()) {
      throw const SessionActionException(
        'This recording is no longer on this phone.',
      );
    }
    final guard = this.guard;
    if (guard == null) {
      throw const SessionActionException(
        'Deleting is not available: the copy on your PC could not be '
        'protected.',
      );
    }
    if (await _mayStillBeSaving(dir, id)) {
      throw const SessionActionException(
        'This recording is still being saved. Try again in a moment.',
      );
    }

    // 1. Make sure the deletion cannot reach the PC. Nothing is deleted if
    //    this fails.
    try {
      await guard.protect(id);
    } on SessionActionException {
      rethrow;
    } catch (_) {
      throw const SessionActionException(
        'The recording was not deleted: the copy on your PC could not be '
        'protected. Try again.',
      );
    }

    // 2. This session's files only: its outbox folder and any of its
    //    leftovers in staging (never synced).
    try {
      await dir.delete(recursive: true);
    } catch (_) {
      throw const SessionActionException(
        'The recording could not be deleted. Try again.',
      );
    }
    final staging = Directory('$filesDir/staging');
    if (await staging.exists()) {
      await for (final entity in staging.list(followLinks: false)) {
        if (entity is File &&
            entity.uri.pathSegments.last.startsWith('${id}_')) {
          try {
            await entity.delete();
          } catch (_) {
            // Staging is private and never synced; a leftover is harmless.
          }
        }
      }
    }

    // 3. Its title, and the guard's follow-up. The folder is already gone,
    //    so failures here do not undo the deletion.
    try {
      await titles.remove(id);
    } catch (_) {}
    try {
      await guard.afterDelete(id);
    } catch (_) {}
  }

  /// No manifest yet and a file changed within [busyWindow].
  Future<bool> _mayStillBeSaving(Directory dir, String id) async {
    if (await File('${dir.path}/${id}_manifest.json').exists()) return false;
    final cutoff = _now().subtract(busyWindow);
    await for (final entity in dir.list(followLinks: false)) {
      if (entity is File && (await entity.lastModified()).isAfter(cutoff)) {
        return true;
      }
    }
    return false;
  }

  /// Reads one session folder: the manifest if present, else the sidecars.
  static Future<SessionSummary> readSession(Directory dir, String id) async {
    final manifest = File('${dir.path}/${id}_manifest.json');
    try {
      if (await manifest.exists()) {
        return _fromManifest(
          id,
          jsonDecode(await manifest.readAsString()) as Map<String, Object?>,
        );
      }
      return await _fromSidecars(dir, id);
    } catch (e) {
      return SessionSummary(
        id: id,
        complete: false,
        chunks: const [],
        start: startFromSessionId(id),
        error: '$e',
      );
    }
  }

  static SessionSummary _fromManifest(String id, Map<String, Object?> json) {
    final chunks = [
      for (final c in (json['chunks'] as List<Object?>? ?? const []))
        _chunk(c! as Map<String, Object?>),
    ]..sort((a, b) => a.seq.compareTo(b.seq));
    final vad = json['vad'] as Map<String, Object?>?;
    final encoder = json['encoder'] as Map<String, Object?>?;
    return SessionSummary(
      id: id,
      complete: true,
      chunks: chunks,
      start:
          _date(json['session_start_wallclock']) ?? startFromSessionId(id),
      end: _date(json['session_end_wallclock']),
      sessionEndMs: _num(json['session_end_ms']),
      recordedMs: _num(json['recorded_ms']),
      failedChunks: (json['failed_chunks'] as List<Object?>?)?.length ?? 0,
      pauseCount: (json['pause_intervals'] as List<Object?>?)?.length ?? 0,
      vadType: vad?['type'] as String?,
      encoderBitrate: (encoder?['bitrate'] as num?)?.toInt(),
    );
  }

  /// No manifest yet (recording, or the app stopped before Stop finished):
  /// the chunk sidecars that have arrived so far.
  static Future<SessionSummary> _fromSidecars(Directory dir, String id) async {
    final chunks = <ChunkSummary>[];
    String? vadType;
    await for (final entity in dir.list(followLinks: false)) {
      if (entity is! File) continue;
      final name = entity.uri.pathSegments.last;
      if (!name.startsWith('${id}_') || !name.endsWith('.json')) continue;
      final json =
          jsonDecode(await entity.readAsString()) as Map<String, Object?>;
      if (json['seq'] == null) continue;
      chunks.add(_chunk(json));
      vadType ??= (json['vad'] as Map<String, Object?>?)?['type'] as String?;
    }
    chunks.sort((a, b) => a.seq.compareTo(b.seq));
    return SessionSummary(
      id: id,
      complete: false,
      chunks: chunks,
      start: startFromSessionId(id),
      vadType: vadType,
    );
  }

  static ChunkSummary _chunk(Map<String, Object?> json) => ChunkSummary(
    seq: (json['seq']! as num).toInt(),
    startMs: _num(json['start_ms']) ?? 0,
    endMs: _num(json['end_ms']) ?? 0,
    opusBytes: (json['opus_bytes'] as num?)?.toInt(),
  );

  static double? _num(Object? v) => (v as num?)?.toDouble();

  static DateTime? _date(Object? v) =>
      v is String ? DateTime.tryParse(v)?.toLocal() : null;
}

/// Local start time encoded in a session ID such as `20261014T142300_a1b2`.
DateTime? startFromSessionId(String id) {
  final m = RegExp(
    r'^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})',
  ).firstMatch(id);
  if (m == null) return null;
  int g(int i) => int.parse(m.group(i)!);
  return DateTime(g(1), g(2), g(3), g(4), g(5), g(6));
}
