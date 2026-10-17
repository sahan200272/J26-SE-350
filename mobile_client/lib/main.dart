import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'capture/audio_capture.dart';
import 'capture/record_audio_capture.dart';
import 'capture/wav_writer.dart';
import 'permissions/microphone_permission.dart';
import 'platform/app_channel.dart';
import 'ui/recording_controller.dart';
import 'ui/recording_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // kDebugMode is a compile-time constant: everything guarded by it is
  // removed from release builds.
  final log = kDebugMode ? debugPrint : null;
  if (kDebugMode) unawaited(_logOpusEncoders());
  // Errors reach each writer, which logs them; until a session starts,
  // nothing else listens.
  final filesDir = kDebugMode ? (appFilesDir()..ignore()) : null;
  runApp(
    EchoVaultApp(
      capture: RecordAudioCapture(log: log),
      debugFrameSinkFactory: kDebugMode
          ? _debugWavSinkFactory(filesDir!)
          : null,
      debugSegmentSinkFactory: kDebugMode
          ? _debugSegmentWavFactory(filesDir!)
          : null,
      log: log,
    ),
  );
}

class EchoVaultApp extends StatelessWidget {
  const EchoVaultApp({
    super.key,
    this.permission = const MethodChannelMicrophonePermission(),
    required this.capture,
    this.screenAwake = const MethodChannelScreenAwake(),
    this.debugFrameSinkFactory,
    this.debugSegmentSinkFactory,
    this.log,
  });

  final MicrophonePermission permission;
  final AudioCapture capture;
  final ScreenAwake screenAwake;
  final FrameSinkFactory? debugFrameSinkFactory;
  final SegmentSinkFactory? debugSegmentSinkFactory;
  final void Function(String message)? log;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Echo Vault',
      theme: ThemeData(colorScheme: .fromSeed(seedColor: Colors.indigo)),
      home: RecordingScreen(
        permission: permission,
        capture: capture,
        screenAwake: screenAwake,
        debugFrameSinkFactory: debugFrameSinkFactory,
        debugSegmentSinkFactory: debugSegmentSinkFactory,
        log: log,
      ),
    );
  }
}

/// Debug only: each session's framed PCM goes to
/// `<app files dir>/debug/<session_id>.wav` so the format can be checked.
FrameSinkFactory _debugWavSinkFactory(Future<String> filesDir) =>
    (sessionId) => WavFileWriter(
      filesDir.then((dir) => '$dir/debug/$sessionId.wav'),
      log: debugPrint,
    );

/// Debug only: each segment goes to
/// `<app files dir>/debug/segments/<session_id>_<seq:05d>.wav`.
SegmentSinkFactory _debugSegmentWavFactory(Future<String> filesDir) =>
    (sessionId) => (segment) {
      final name = '${sessionId}_${segment.seq.toString().padLeft(5, '0')}.wav';
      unawaited(
        filesDir
            .then(
              (dir) =>
                  writeWavFile('$dir/debug/segments/$name', segment.samples),
            )
            .then(
              (_) => debugPrint(
                '[wav] wrote segments/$name: ${segment.samples.length} samples',
              ),
              onError: (Object e) =>
                  debugPrint('[wav] segments/$name: write failed: $e'),
            ),
      );
    };

/// Debug only: logs the device's Opus encoders once (A2 check for A4).
Future<void> _logOpusEncoders() async {
  try {
    final encoders = await listOpusEncoders();
    debugPrint('[A2] listOpusEncoders: ${jsonEncode(encoders)}');
  } catch (e) {
    debugPrint('[A2] listOpusEncoders failed: $e');
  }
}
