import 'package:flutter/services.dart';

/// The app's single MethodChannel to `MainActivity.kt` (platform APIs only,
/// no third-party plugin). Methods:
///
/// - `requestMicrophone` → `granted` | `denied` | `permanentlyDenied`
/// - `setKeepScreenOn(bool)` → toggles `FLAG_KEEP_SCREEN_ON`
/// - `getFilesDir` → app-private `files/` directory (absolute path)
/// - `listOpusEncoders` → Opus encoders in `MediaCodecList(REGULAR_CODECS)`
///
/// The name dates from A1, when it only handled the permission.
const appChannel = MethodChannel('lk.sliit.j26se350.echo_vault/permissions');

/// Keeps the display on while a session is open (recording or paused).
abstract interface class ScreenAwake {
  Future<void> setKeepScreenOn(bool on);
}

class MethodChannelScreenAwake implements ScreenAwake {
  const MethodChannelScreenAwake();

  @override
  Future<void> setKeepScreenOn(bool on) =>
      appChannel.invokeMethod<void>('setKeepScreenOn', on);
}

/// Absolute path of the app-private `files/` directory
/// (`Context.getFilesDir()`).
Future<String> appFilesDir() async {
  final dir = await appChannel.invokeMethod<String>('getFilesDir');
  if (dir == null || dir.isEmpty) {
    throw PlatformException(code: 'NO_FILES_DIR', message: 'getFilesDir');
  }
  return dir;
}

/// Opus encoders reported by Android's `MediaCodecList(REGULAR_CODECS)`, one
/// map per codec (name, sample rates, channel counts, bitrate range, …).
/// Informational only (A2 check for A4).
Future<List<Map<String, Object?>>> listOpusEncoders() async {
  final list = await appChannel.invokeListMethod<Object?>('listOpusEncoders');
  return [
    for (final item in list ?? const <Object?>[])
      Map<String, Object?>.from(item! as Map),
  ];
}
