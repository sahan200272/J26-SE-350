import 'dart:async';

import 'package:echo_vault/permissions/microphone_permission.dart';

/// [MicrophonePermission] that answers with [status], waits for [completer]
/// when one is set, or throws [error] when one is set.
class FakeMicrophonePermission implements MicrophonePermission {
  FakeMicrophonePermission([this.status = MicPermissionStatus.granted]);

  MicPermissionStatus status;
  Completer<MicPermissionStatus>? completer;
  Object? error;
  int requestCount = 0;

  @override
  Future<MicPermissionStatus> request() async {
    requestCount++;
    if (error != null) throw error!;
    return completer?.future ?? status;
  }
}
