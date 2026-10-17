import 'dart:async';

import 'package:flutter/services.dart';

import '../platform/app_channel.dart';
import 'syncthing_status.dart';

/// The embedded Syncthing (A5), controlled natively by `SyncthingController`
/// (started with the app, LAN-only). Behind an interface for tests.
abstract interface class SyncthingClient {
  /// Starts Syncthing if it is not running (idempotent).
  Future<SyncthingStatus> start();

  Future<SyncthingStatus> status();

  /// Sets the one PC to send to and shares the outbox with it. Throws a
  /// [PlatformException] with code `BAD_PEER` if Syncthing rejects the ID or
  /// the address.
  Future<SyncthingStatus> setPeer({
    required String deviceId,
    required String address,
  });

  /// Scans [sub] (a path inside the outbox) now, so a new file is offered to
  /// the PC without waiting for the file watcher.
  Future<bool> scan(String sub);

  /// PNG of this phone's device ID as a QR code.
  Future<Uint8List> qrPng();
}

class MethodChannelSyncthingClient implements SyncthingClient {
  const MethodChannelSyncthingClient();

  @override
  Future<SyncthingStatus> start() => _status('syncthingStart');

  @override
  Future<SyncthingStatus> status() => _status('syncthingStatus');

  @override
  Future<SyncthingStatus> setPeer({
    required String deviceId,
    required String address,
  }) => _status('syncthingSetPeer', {'deviceId': deviceId, 'address': address});

  @override
  Future<bool> scan(String sub) async =>
      await appChannel.invokeMethod<bool>('syncthingScan', {'sub': sub}) ??
      false;

  @override
  Future<Uint8List> qrPng() async {
    final png = await appChannel.invokeMethod<Uint8List>('syncthingQr');
    if (png == null || png.isEmpty) {
      throw PlatformException(code: 'NO_QR', message: 'syncthingQr');
    }
    return png;
  }

  Future<SyncthingStatus> _status(String method, [Object? arguments]) async {
    final map = await appChannel.invokeMapMethod<Object?, Object?>(
      method,
      arguments,
    );
    if (map == null) {
      throw PlatformException(code: 'NO_STATUS', message: method);
    }
    return SyncthingStatus.fromMap(map);
  }
}

/// For `ChunkPipeline.onPublished`: asks Syncthing to scan each file of
/// session [sessionId] as soon as it is renamed into the outbox, so it goes
/// to the PC within about a second instead of after the watcher delay.
/// Failures are only logged: the file stays in the outbox, and the watcher
/// (or a later scan) picks it up.
void Function(String fileName) scanOnPublish(
  SyncthingClient syncthing,
  String sessionId, {
  void Function(String message)? log,
}) => (fileName) {
  final sub = '$sessionId/$fileName';
  unawaited(
    syncthing.scan(sub).then((scanned) {
      if (!scanned) {
        log?.call('[sync] $sub: Syncthing not running, scan skipped');
      }
    }, onError: (Object e) => log?.call('[sync] $sub: scan failed: $e')),
  );
};
