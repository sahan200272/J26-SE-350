import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'capture/audio_capture.dart';
import 'capture/record_audio_capture.dart';
import 'capture/wav_writer.dart';
import 'encoding/method_channel_opus_encoder.dart';
import 'encoding/opus_encoder.dart';
import 'permissions/microphone_permission.dart';
import 'platform/app_channel.dart';
import 'sessions/session_store.dart';
import 'sync/syncthing_client.dart';
import 'sync/syncthing_session_guard.dart';
import 'transfer/chunk_pipeline.dart';
import 'ui/about_screen.dart';
import 'ui/app_shell.dart';
import 'ui/onboarding_screen.dart';
import 'ui/onboarding_store.dart';
import 'ui/recording_controller.dart';
import 'ui/recording_screen.dart';
import 'ui/splash_screen.dart';
import 'ui/theme/app_theme.dart';
import 'ui/theme/ember_theme.dart';

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
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      statusBarBrightness: Brightness.dark,
      systemNavigationBarColor: EvEmber.black,
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );
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
      showSplash: true,
      onboardingStore: FileOnboardingStore(filesDir),
      // Deleting a recording first makes Syncthing ignore it, so the PC
      // keeps its copy.
      sessions: OutboxSessionStore(
        filesDir,
        guard: const SyncthingRemoteCopyGuard(syncthing),
      ),
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
    this.showSplash = false,
    this.onboardingStore,
    this.sessions,
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

  /// Show the branded splash before the app (on in `main`).
  final bool showSplash;

  /// First-run welcome screens; skipped when null.
  final OnboardingStore? onboardingStore;

  /// Sessions tab data; the tab is hidden when null.
  final SessionSource? sessions;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Echo Vault',
      debugShowCheckedModeBanner: false,
      theme: buildEchoVaultTheme(),
      home: _AppGate(app: this),
    );
  }
}

enum _Phase { splash, loading, onboarding, app }

/// Splash → (first run only) welcome screens → app shell.
class _AppGate extends StatefulWidget {
  const _AppGate({required this.app});

  final EchoVaultApp app;

  @override
  State<_AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<_AppGate> {
  late _Phase _phase;
  Future<bool>? _onboarded;
  bool _splashDone = false;

  EchoVaultApp get app => widget.app;

  @override
  void initState() {
    super.initState();
    _onboarded = app.onboardingStore?.isComplete();
    if (app.showSplash) {
      _phase = _Phase.splash;
    } else if (_onboarded == null) {
      _phase = _Phase.app;
    } else {
      _phase = _Phase.loading;
      unawaited(_afterSplash());
    }
  }

  Future<void> _afterSplash() async {
    _splashDone = true;
    final onboarded = await (_onboarded ?? Future.value(true));
    if (!mounted) return;
    setState(() => _phase = onboarded ? _Phase.app : _Phase.onboarding);
  }

  void _finishOnboarding() {
    unawaited(app.onboardingStore?.markComplete());
    setState(() => _phase = _Phase.app);
  }

  void _showWelcomeAgain() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      fullscreenDialog: true,
      builder: (context) =>
          OnboardingScreen(onDone: () => Navigator.of(context).pop()),
    ),
  );

  Widget _shell() => AppShell(
    sessions: app.sessions,
    syncthing: app.syncthing,
    appVersion: app.appVersion,
    onShowWelcome: _showWelcomeAgain,
    // Opened only when the user taps Start recording; it starts at once.
    recordingBuilder: (_) => RecordingScreen(
      permission: app.permission,
      capture: app.capture,
      screenAwake: app.screenAwake,
      chunkPipelineFactory: app.chunkPipelineFactory,
      debugFrameSinkFactory: app.debugFrameSinkFactory,
      debugSegmentSinkFactory: app.debugSegmentSinkFactory,
      appVersion: app.appVersion,
      log: app.log,
      autoStart: true,
      // After Stop: name the recording with the existing rename.
      renameRecording: app.sessions?.rename,
    ),
  );

  @override
  Widget build(BuildContext context) {
    final child = switch (_phase) {
      _Phase.splash => SplashScreen(
        key: const ValueKey(_Phase.splash),
        onFinished: () {
          if (!_splashDone) unawaited(_afterSplash());
        },
      ),
      _Phase.loading => const LaunchPlaceholder(
        key: ValueKey(_Phase.loading),
      ),
      _Phase.onboarding => OnboardingScreen(
        key: const ValueKey(_Phase.onboarding),
        onDone: _finishOnboarding,
      ),
      _Phase.app => KeyedSubtree(
        key: const ValueKey(_Phase.app),
        child: _shell(),
      ),
    };
    return AnimatedSwitcher(
      duration: EvMotion.reduced(context) ? Duration.zero : EvMotion.slow,
      switchInCurve: EvMotion.curve,
      switchOutCurve: Curves.easeIn,
      child: child,
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
