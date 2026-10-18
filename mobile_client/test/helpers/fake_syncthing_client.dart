import 'package:echo_vault/sync/syncthing_client.dart';
import 'package:echo_vault/sync/syncthing_status.dart';
import 'package:flutter/services.dart';

/// [SyncthingClient] whose answers are set by the test.
class FakeSyncthingClient implements SyncthingClient {
  FakeSyncthingClient({SyncthingStatus? status})
    : current = status ?? runningStatus();

  /// Returned by [start], [status] and (updated) by [setPeer].
  SyncthingStatus current;

  /// Method calls received, in order, e.g. `status`, `scan:<sub>`.
  final List<String> calls = [];

  /// When set, [setPeer] throws it.
  PlatformException? setPeerError;

  /// When set, [scan] throws it; otherwise [scan] returns [scanResult].
  Object? scanError;
  bool scanResult = true;

  /// A valid 1×1 transparent PNG.
  static final png = Uint8List.fromList(const [
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, //
    0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
    0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
    0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
    0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
  ]);

  @override
  Future<SyncthingStatus> start() async {
    calls.add('start');
    return current;
  }

  @override
  Future<SyncthingStatus> status() async {
    calls.add('status');
    return current;
  }

  @override
  Future<SyncthingStatus> setPeer({
    required String deviceId,
    required String address,
  }) async {
    calls.add('setPeer:$deviceId@$address');
    if (setPeerError case final e?) throw e;
    current = runningStatus(pcDeviceId: deviceId, pcAddress: address);
    return current;
  }

  @override
  Future<bool> scan(String sub) async {
    calls.add('scan:$sub');
    if (scanError case final e?) throw e;
    return scanResult;
  }

  @override
  Future<Uint8List> qrPng() async {
    calls.add('qr');
    return png;
  }

  /// When set, [protectSession] throws it.
  Object? protectError;

  /// Returned by [sessionPendingFiles].
  int? pendingForSession;

  @override
  Future<void> protectSession(String sessionId) async {
    calls.add('protect:$sessionId');
    if (protectError case final e?) throw e;
  }

  @override
  Future<int?> sessionPendingFiles(String sessionId) async {
    calls.add('pending:$sessionId');
    return pendingForSession;
  }
}

const phoneId =
    'KBPELAQ-CF7A2I5-U256OND-WXIL6DT-VBOI6DC-42QB6MH-WA4644A-6VPQQQL';
const pcId = 'BLX76HI-LIX6UFG-72BTSUV-ZR6HOYY-NPNDCOQ-TOWEIRN-YCCS67U-Q7YWEA5';

SyncthingStatus runningStatus({
  String? pcDeviceId,
  String? pcAddress,
  bool pcConnected = false,
  String? remoteState,
  int? pendingChunks,
  bool lanOnlyVerified = true,
}) => SyncthingStatus(
  running: true,
  version: 'v2.1.6',
  deviceId: phoneId,
  lanOnlyVerified: lanOnlyVerified,
  listeners: const ['tcp://0.0.0.0:22000'],
  discovery: const ['IPv4 local'],
  folderId: 'echo-vault-outbox',
  folderState: 'idle',
  pcDeviceId: pcDeviceId,
  pcAddress: pcAddress,
  pcConnected: pcConnected,
  pcConnectionAddress: pcConnected ? '192.168.1.20:22000' : null,
  pcConnectionType: pcConnected ? 'tcp-client' : null,
  remoteState: remoteState,
  pendingChunks: pendingChunks ?? (pcDeviceId == null ? null : 0),
);
