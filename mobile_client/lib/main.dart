import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'capture/audio_capture.dart';
import 'capture/record_audio_capture.dart';
import 'capture/wav_writer.dart';
import 'encoding/method_channel_opus_encoder.dart';
import 'encoding/opus_encoder.dart';
import 'permissions/microphone_permission.dart';
import 'platform/app_channel.dart';
import 'sync/syncthing_client.dart';
import 'transfer/chunk_pipeline.dart';
import 'ui/about_screen.dart';
import 'ui/recording_controller.dart';
import 'ui/recording_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // kDebugMode is a compile-time constant: everything guarded by it is
  // removed from release builds.
  final log = kDebugMode ? debugPrint : null;
  if (kDebugMode) unawaited(_logOpusEncoders());
  // Errors reach each user (writer or pipeline), which logs them; until a
  // session starts, nothing else listens.
  final filesDir = appFilesDir()..ignore();
  final version = appVersion()..ignore();
  // Syncthing starts natively with the activity (LAN-only, A5). Coming back
  // to the foreground restarts it if it has stopped.
  const syncthing = MethodChannelSyncthingClient();
  unawaited(_startSyncthing(syncthing, log));
  AppLifecycleListener(
    onResume: () => unawaited(_startSyncthing(syncthing, log)),
  );
  LicenseRegistry.addLicense(_syncthingLicense);
  runApp(
    EchoVaultApp(
      capture: RecordAudioCapture(log: log),
      chunkPipelineFactory: (session) => ChunkPipeline(
        sessionId: session.id!,
        encoder: const MethodChannelOpusEncoder(bitrate: kDefaultOpusBitrate),
        filesDir: filesDir,
        appVersion: version,
        log: log,
        // Offer each file to the PC as soon as it is in the outbox.
        onPublished: scanOnPublish(syncthing, session.id!, log: log),
      ),
      debugFrameSinkFactory: kDebugMode ? _debugWavSinkFactory(filesDir) : null,
      debugSegmentSinkFactory: kDebugMode
          ? _debugSegmentWavFactory(filesDir)
          : null,
      syncthing: syncthing,
      appVersion: version,
      log: log,
    ),
  );
}

Future<void> _startSyncthing(
  SyncthingClient syncthing,
  void Function(String message)? log,
) async {
  try {
    final s = await syncthing.start();
    log?.call(
      s.running
          ? '[sync] Syncthing ${s.version} running, LAN-only verified: '
                '${s.lanOnlyVerified}, listeners ${s.listeners}, discovery '
                '${s.discovery}, ${s.connectionLabel}'
                '${s.pendingLabel == null ? '' : ', ${s.pendingLabel}'}'
          : '[sync] Syncthing not running: ${s.error}',
    );
  } catch (e) {
    log?.call('[sync] start failed: $e');
  }
}

Stream<LicenseEntry> _syncthingLicense() async* {
  yield LicenseEntryWithLineBreaks([
    'Syncthing $kSyncthingVersion',
  ], await loadSyncthingLicense());
}

class EchoVaultApp extends StatelessWidget {
  const EchoVaultApp({
    super.key,
    this.permission = const MethodChannelMicrophonePermission(),
    required this.capture,
    this.screenAwake = const MethodChannelScreenAwake(),
    this.chunkPipelineFactory,
    this.debugFrameSinkFactory,
    this.debugSegmentSinkFactory,
    this.syncthing,
    this.appVersion,
    this.log,
  });

  final MicrophonePermission permission;
  final AudioCapture capture;
  final ScreenAwake screenAwake;
  final ChunkPipelineFactory? chunkPipelineFactory;
  final FrameSinkFactory? debugFrameSinkFactory;
  final SegmentSinkFactory? debugSegmentSinkFactory;
  final SyncthingClient? syncthing;
  final Future<String>? appVersion;
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
        chunkPipelineFactory: chunkPipelineFactory,
        debugFrameSinkFactory: debugFrameSinkFactory,
        debugSegmentSinkFactory: debugSegmentSinkFactory,
        syncthing: syncthing,
        appVersion: appVersion,
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
