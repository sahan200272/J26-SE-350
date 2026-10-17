import 'package:flutter/services.dart';

/// Outcome of asking the user for microphone access.
enum MicPermissionStatus {
  granted,
  denied,

  /// Denied with "don't ask again"; only the system settings can change it.
  permanentlyDenied,
}

/// Requests microphone access. Abstracted so the UI can be tested without a
/// platform.
abstract interface class MicrophonePermission {
  Future<MicPermissionStatus> request();
}

/// Talks to `MainActivity.kt`, which uses the Android runtime permission APIs
/// directly (no third-party plugin).
class MethodChannelMicrophonePermission implements MicrophonePermission {
  const MethodChannelMicrophonePermission();

  static const channel = MethodChannel(
    'lk.sliit.j26se350.echo_vault/permissions',
  );

  @override
  Future<MicPermissionStatus> request() async {
    final result = await channel.invokeMethod<String>('requestMicrophone');
    return switch (result) {
      'granted' => MicPermissionStatus.granted,
      'permanentlyDenied' => MicPermissionStatus.permanentlyDenied,
      _ => MicPermissionStatus.denied,
    };
  }
}
