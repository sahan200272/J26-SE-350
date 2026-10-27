/// File names and folders of the transfer layer (CLAUDE.md conventions).
///
/// Files are written to `files/staging/` and then renamed into
/// `files/outbox/<session_id>/`, which is the only folder that is synced.
library;

/// `<session_id>_<seq:05d>`, e.g. `20261014T142300_a1b2_00007`.
String chunkBaseName(String sessionId, int seq) =>
    '${sessionId}_${seq.toString().padLeft(5, '0')}';

/// `<session_id>_<seq:05d>.opus`
String chunkAudioName(String sessionId, int seq) =>
    '${chunkBaseName(sessionId, seq)}.opus';

/// `<session_id>_<seq:05d>.json`
String chunkSidecarName(String sessionId, int seq) =>
    '${chunkBaseName(sessionId, seq)}.json';

/// `<session_id>_manifest.json`
String manifestName(String sessionId) => '${sessionId}_manifest.json';

/// Staging and outbox folders under the app's private `files/` directory.
class OutboxLayout {
  const OutboxLayout(this.filesDir);

  final String filesDir;

  /// Where files are written first (never synced).
  String get stagingDir => '$filesDir/staging';

  /// Where finished files appear, one complete file per rename.
  String sessionDir(String sessionId) => '$filesDir/outbox/$sessionId';
}
