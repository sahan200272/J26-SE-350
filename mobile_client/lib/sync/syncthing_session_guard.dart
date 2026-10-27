import '../sessions/session_store.dart';
import 'syncthing_client.dart';

/// [RemoteCopyGuard] backed by the embedded Syncthing: before a session
/// folder is deleted, Syncthing is told to ignore it, so the deletion is not
/// sent to the PC and the PC keeps its copy.
class SyncthingRemoteCopyGuard implements RemoteCopyGuard {
  const SyncthingRemoteCopyGuard(this.syncthing);

  final SyncthingClient syncthing;

  @override
  Future<void> protect(String sessionId) =>
      syncthing.protectSession(sessionId);

  @override
  Future<void> afterDelete(String sessionId) async {}
}
