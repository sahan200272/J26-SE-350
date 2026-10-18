/// User-chosen recording titles, kept in the app-private
/// `files/prefs/session_titles.json` (outside the synced outbox, excluded
/// from Android backup like all app data). Session files are never touched.
///
/// Pure Dart (dart:io), no Flutter imports.
library;

import 'dart:convert';
import 'dart:io';

/// Longest title accepted, in characters.
const kMaxSessionTitleLength = 60;

/// [raw] with surrounding whitespace removed, inner runs of whitespace
/// (including line breaks) collapsed to one space, control characters
/// dropped and the length capped at [kMaxSessionTitleLength]. Null when
/// nothing is left.
String? normalizeSessionTitle(String raw) {
  final cleaned = raw
      .replaceAll(RegExp(r'[\u0000-\u0008\u000B-\u001F\u007F]'), '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (cleaned.isEmpty) return null;
  final runes = cleaned.runes.toList();
  return runes.length <= kMaxSessionTitleLength
      ? cleaned
      : String.fromCharCodes(runes.take(kMaxSessionTitleLength)).trimRight();
}

/// Reads and writes the titles file. Writes go to a temporary file first and
/// are then renamed over the old one, so a crash never leaves a half-written
/// file.
class SessionTitleStore {
  SessionTitleStore(this._filesDir);

  final Future<String> _filesDir;

  static const _schema = 'echo-vault-titles/1';

  Future<File> _file() async =>
      File('${await _filesDir}/prefs/session_titles.json');

  /// All titles by session ID; empty if none were set or the file is
  /// unreadable (titles then fall back to the automatic ones).
  Future<Map<String, String>> load() async {
    try {
      final file = await _file();
      if (!await file.exists()) return {};
      final json = jsonDecode(await file.readAsString());
      final titles = (json as Map<String, Object?>)['titles'];
      if (titles is! Map) return {};
      return {
        for (final MapEntry(:key, :value) in titles.entries)
          if (value is String && value.isNotEmpty) '$key': value,
      };
    } catch (_) {
      return {};
    }
  }

  Future<void> setTitle(String sessionId, String title) async {
    final titles = await load();
    titles[sessionId] = title;
    await _save(titles);
  }

  Future<void> remove(String sessionId) async {
    final titles = await load();
    if (titles.remove(sessionId) != null) await _save(titles);
  }

  Future<void> _save(Map<String, String> titles) async {
    final file = await _file();
    await file.parent.create(recursive: true);
    final tmp = File('${file.path}.tmp');
    await tmp.writeAsString(
      const JsonEncoder.withIndent(
        '  ',
      ).convert({'schema_version': _schema, 'titles': titles}),
      flush: true,
    );
    await tmp.rename(file.path);
  }
}
