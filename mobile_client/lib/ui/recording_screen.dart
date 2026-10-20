import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../capture/audio_capture.dart';
import '../permissions/microphone_permission.dart';
import '../platform/app_channel.dart';
import '../session/clock.dart';
import '../session/recording_session.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'display_format.dart';
import 'elapsed_format.dart';
import 'ember_components.dart';
import 'immersive_backdrop.dart';
import 'input_level_meter.dart';
import 'lifecycle_source.dart';
import 'live_waveform.dart';
import 'recording_controller.dart';
import 'save_recording_sheet.dart';
import 'settings_screen.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Recording screen: status (ready / recording / paused / stopped), a large
/// timer, a live waveform of the microphone level, and the controls: Start
/// when no session is open, Pause/Resume and Stop while one is. Recording
/// only ever starts from a user action (Start here, or the microphone on
/// Home, which opens this screen with [autoStart]).
///
/// After the user taps Stop, and when [renameRecording] is set, the
/// "Name this recording" sheet is offered. The recording is saved by Stop
/// as before; the sheet only names it.
class RecordingScreen extends StatefulWidget {
  const RecordingScreen({
    super.key,
    required this.permission,
    required this.capture,
    this.screenAwake = const MethodChannelScreenAwake(),
    this.lifecycle = const AppLifecycleSource(),
    this.clock,
    this.wallClock,
    this.random,
    this.chunkPipelineFactory,
    this.debugFrameSinkFactory,
    this.debugSegmentSinkFactory,
    this.syncthing,
    this.appVersion,
    this.log,
    this.onSessionOpenChanged,
    this.autoStart = false,
    this.renameRecording,
    this.openSettings = openAppSettings,
    this.doubleTapGuard = const Duration(milliseconds: 600),
  });

  /// Opens the PC connection settings from the app bar; no button when null.
  final SyncthingClient? syncthing;
  final Future<String>? appVersion;

  static const settingsKey = Key('sync-settings-button');
  static const doneKey = Key('recording-done');
  static const openSettingsKey = Key('open-app-settings');

  /// Shown when Android Settings could not be opened.
  static const openSettingsFailedMessage =
      'Settings could not be opened. Open Settings › Apps › Echo Vault › '
      'Permissions › Microphone and allow it.';

  /// Shown when the user tries to leave while a session is open.
  static const leaveBlockedMessage =
      'Stop the recording before leaving this screen.';

  final MicrophonePermission permission;
  final AudioCapture capture;
  final ScreenAwake screenAwake;
  final LifecycleSource lifecycle;
  final Clock? clock;
  final DateTime Function()? wallClock;
  final Random? random;
  final ChunkPipelineFactory? chunkPipelineFactory;
  final FrameSinkFactory? debugFrameSinkFactory;
  final SegmentSinkFactory? debugSegmentSinkFactory;
  final void Function(String message)? log;

  /// Called with true when a session opens (recording or paused) and false
  /// when it stops.
  final ValueChanged<bool>? onSessionOpenChanged;

  /// Press Start once when the screen opens. Only used when the user opened
  /// this screen by tapping "Start recording".
  final bool autoStart;

  /// Gives a stored recording a title (the existing session rename). When
  /// set, the naming sheet is shown after Stop; when null it is not.
  final Future<void> Function(String sessionId, String title)? renameRecording;

  /// Opens this app's page in Android Settings (for a blocked
  /// microphone); false when it could not be opened.
  final Future<bool> Function() openSettings;

  /// Right after Start, Stop is ignored for this long, and right after
  /// Stop, Start ("Record again") is: Start and Stop sit in the same place,
  /// so a double tap must not start and stop (or stop and restart) a
  /// recording. No confirmation step. [Duration.zero] turns it off.
  final Duration doubleTapGuard;

  @override
  State<RecordingScreen> createState() => _RecordingScreenState();
}

class _RecordingScreenState extends State<RecordingScreen> {
  late final RecordingController _controller = RecordingController(
    permission: widget.permission,
    capture: widget.capture,
    screenAwake: widget.screenAwake,
    lifecycle: widget.lifecycle,
    clock: widget.clock,
    wallClock: widget.wallClock,
    random: widget.random,
    chunkPipelineFactory: widget.chunkPipelineFactory,
    debugFrameSinkFactory: widget.debugFrameSinkFactory,
    debugSegmentSinkFactory: widget.debugSegmentSinkFactory,
    log: widget.log,
  );

  static const _maxLevels = 48;
  List<double> _levels = const [];
  bool _sessionOpen = false;

  /// The user tapped Stop (not a capture failure): offer the naming sheet.
  bool _stopPressed = false;

  /// The last waveform levels of the session that just stopped.
  List<double> _finalLevels = const [];

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onControllerChanged);
    if (widget.autoStart) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _controller.canStart) _controller.start();
      });
    }
  }

  void _onControllerChanged() {
    final state = _controller.state;
    // Waveform: one level sample per controller update while audio flows.
    if (state == SessionState.recording && !_controller.isStartingCapture) {
      final level = InputLevelMeter.fraction(_controller.inputLevelDbfs);
      final next = [..._levels, level];
      _levels = List.unmodifiable(
        next.length > _maxLevels
            ? next.sublist(next.length - _maxLevels)
            : next,
      );
    } else if (state == SessionState.idle || state == SessionState.stopped) {
      if (_levels.isNotEmpty) {
        _finalLevels = _levels;
        _levels = const [];
      }
    }

    final open = switch (state) {
      SessionState.recording || SessionState.paused => true,
      SessionState.idle || SessionState.stopped => false,
    };
    if (open != _sessionOpen) {
      _sessionOpen = open;
      widget.onSessionOpenChanged?.call(open);
      if (open) {
        _finalLevels = const [];
      } else if (state == SessionState.stopped && _stopPressed) {
        _offerNaming();
      }
      _stopPressed = false;
      if (mounted) setState(() {}); // Updates PopScope.canPop.
    }
  }

  /// Set for [RecordingScreen.doubleTapGuard] after Start and after Stop.
  bool _guarded = false;
  Timer? _guardTimer;

  void _armGuard() {
    final guard = widget.doubleTapGuard;
    if (guard <= Duration.zero) return;
    _guarded = true;
    _guardTimer?.cancel();
    _guardTimer = Timer(guard, () => _guarded = false);
  }

  /// A short haptic tick for each control (no permission needed).
  static void _haptic(Future<void> Function() feedback) =>
      unawaited(feedback().catchError((Object _) {}));

  void _start() {
    if (_guarded || !_controller.canStart) return;
    _haptic(HapticFeedback.mediumImpact);
    _controller.start();
    _armGuard();
  }

  void _pauseOrResume() {
    if (_controller.state == SessionState.paused) {
      if (!_controller.canResume) return;
      _haptic(HapticFeedback.selectionClick);
      _controller.resume();
    } else {
      if (!_controller.canPause) return;
      _haptic(HapticFeedback.selectionClick);
      _controller.pause();
    }
  }

  void _stop() {
    if (_guarded || !_controller.canStop) return;
    _haptic(HapticFeedback.heavyImpact);
    _stopPressed = true;
    _controller.stop();
    _armGuard();
  }

  /// After Stop: the "Name this recording" sheet. Saving the audio is not
  /// part of it (Stop already saves); Save only renames, Cancel keeps the
  /// automatic name.
  void _offerNaming() {
    final rename = widget.renameRecording;
    final pipeline = _controller.chunkPipeline;
    final id = _controller.sessionId;
    if (rename == null || pipeline == null || id == null) return;
    final start = _controller.startWallClock;
    final defaultTitle = start == null
        ? 'Recording'
        : 'Recording at ${formatClock(start)}';
    final duration = _controller.elapsed;
    final levels = _finalLevels;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final title = await showSaveRecordingSheet(
        context,
        defaultTitle: defaultTitle,
        duration: duration,
        levels: levels,
        saved: pipeline.manifest,
        onRename: (name) => rename(id, name),
      );
      if (title == null || !mounted) return;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text('Saved as “$title”')));
      // Back to where recording was started (Home), which then refreshes.
      if (Navigator.of(context).canPop()) {
        await Navigator.of(context).maybePop();
      }
    });
  }

  @override
  void dispose() {
    _guardTimer?.cancel();
    _controller.removeListener(_onControllerChanged);
    _controller.dispose();
    super.dispose();
  }

  void _blockedLeave() {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        const SnackBar(content: Text(RecordingScreen.leaveBlockedMessage)),
      );
  }

  /// Microphone blocked: open this app's page in Android Settings, or say
  /// where to find it when that is not possible.
  Future<void> _openSettings() async {
    final opened = await widget.openSettings();
    if (opened || !mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        const SnackBar(
          content: Text(RecordingScreen.openSettingsFailedMessage),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final canLeave = Navigator.of(context).canPop();
    return EmberScope(
      child: PopScope(
        canPop: !_sessionOpen,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) _blockedLeave();
        },
        child: Scaffold(
          backgroundColor: EvEmber.black,
          extendBodyBehindAppBar: true,
          appBar: AppBar(
            backgroundColor: Colors.transparent,
            surfaceTintColor: Colors.transparent,
            scrolledUnderElevation: 0,
            automaticallyImplyLeading: false,
            leading: canLeave
                ? Center(
                    child: GlassIconButton(
                      icon: Icons.arrow_back_rounded,
                      tooltip: 'Back',
                      // Through PopScope: refused while a session is open.
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                  )
                : null,
            title: const BrandTitle(),
            centerTitle: true,
            actions: [
              if (widget.syncthing case final syncthing?)
                ListenableBuilder(
                  listenable: _controller,
                  // Only between sessions: the recording indicator (FR1)
                  // must stay on screen while a session is open.
                  builder: (context, _) => GlassIconButton(
                    buttonKey: RecordingScreen.settingsKey,
                    tooltip: 'Connect to your PC',
                    icon: Icons.sync_rounded,
                    onPressed: switch (_controller.state) {
                      SessionState.idle ||
                      SessionState.stopped => () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => SettingsScreen(
                            syncthing: syncthing,
                            appVersion: widget.appVersion,
                          ),
                        ),
                      ),
                      _ => null,
                    },
                  ),
                ),
              const SizedBox(width: EvSpace.xs),
            ],
          ),
          body: Stack(
            fit: StackFit.expand,
            children: [
              // The same photo, blur and glass layers as Home (no video).
              const ImmersiveBackdrop(),
              SafeArea(
                child: ListenableBuilder(
                  listenable: _controller,
                  builder: (context, _) => Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: EvSpace.xs),
                      const _Heading(),
                      Expanded(
                        child: LayoutBuilder(
                          builder: (context, box) => SingleChildScrollView(
                            child: ConstrainedBox(
                              constraints: BoxConstraints(
                                minHeight: box.maxHeight,
                              ),
                              child: Center(
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(
                                    vertical: EvSpace.md,
                                  ),
                                  child: _StatusView(
                                    controller: _controller,
                                    levels: _levels,
                                    onDone: canLeave
                                        ? () => Navigator.of(context).maybePop()
                                        : null,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(
                          EvSpace.lg,
                          0,
                          EvSpace.lg,
                          EvSpace.md,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (_controller.message case final message?) ...[
                              _PermissionMessage(
                                message: message,
                                onOpenSettings:
                                    message ==
                                        RecordingController
                                            .permanentlyDeniedMessage
                                    ? () => unawaited(_openSettings())
                                    : null,
                              ),
                              const SizedBox(height: EvSpace.md),
                            ],
                            _Controls(
                              controller: _controller,
                              onStart: _start,
                              onPauseResume: _pauseOrResume,
                              onStop: _stop,
                            ),
                            const SizedBox(height: EvSpace.md),
                            const _PrivacyFootnote(),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The screen's quiet title.
class _Heading extends StatelessWidget {
  const _Heading();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: EvSpace.lg),
      child: Column(
        children: [
          Text(
            'Capture what matters',
            textAlign: TextAlign.center,
            style: textTheme.titleLarge?.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: EvSpace.xxs),
          Text(
            'Your conversations stay under your control.',
            textAlign: TextAlign.center,
            style: textTheme.bodyMedium?.copyWith(color: EvEmber.textSoft),
          ),
        ],
      ),
    );
  }
}

class _StatusView extends StatelessWidget {
  const _StatusView({
    required this.controller,
    required this.levels,
    required this.onDone,
  });

  final RecordingController controller;
  final List<double> levels;
  final VoidCallback? onDone;

  static const double _waveHeight = 200;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final muted = textTheme.bodyMedium?.copyWith(color: EvEmber.textSoft);
    final elapsed = formatElapsed(controller.elapsed);
    const gap = SizedBox(height: EvSpace.lg);
    Widget padded(Widget child) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: EvSpace.lg),
      child: child,
    );
    final view = switch (controller.state) {
      SessionState.recording when controller.isStartingCapture => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const LiveWaveform(levels: [], active: false, height: _waveHeight),
          gap,
          padded(StartingIndicator(elapsed: elapsed)),
        ],
      ),
      SessionState.recording => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Edge to edge; its height follows the real input level.
          LiveWaveform(
            levels: levels,
            height: _waveHeight,
            bars: 48,
            color: controller.isSpeechDetected
                ? EvEmber.accentSoft
                : const Color(0xFFFFC2B8),
          ),
          gap,
          padded(RecordingIndicator(elapsed: elapsed)),
          const SizedBox(height: EvSpace.md),
          padded(SpeechStatus(speech: controller.isSpeechDetected)),
        ],
      ),
      SessionState.paused => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          LiveWaveform(levels: levels, active: false, height: _waveHeight),
          gap,
          padded(PausedIndicator(elapsed: elapsed)),
          if (controller.pauseReason == PauseReason.autoBackground) ...[
            gap,
            padded(const AutoPauseNotice()),
          ] else ...[
            const SizedBox(height: EvSpace.md),
            padded(
              Text(
                'Nothing is being recorded while paused.',
                style: muted,
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ],
      ),
      SessionState.idle => padded(
        Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const _MicBadge(),
            gap,
            Text(
              controller.isRequestingPermission
                  ? 'Requesting microphone access…'
                  : 'Ready to record',
              style: textTheme.headlineSmall?.copyWith(color: Colors.white),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: EvSpace.xs),
            Text(
              'Recording begins when you tap Start and ends when you tap Stop.',
              style: muted,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
      SessionState.stopped => padded(
        Column(
          key: const Key('stopped-summary'),
          mainAxisSize: MainAxisSize.min,
          children: [
            const StatusPill(
              label: 'Stopped',
              icon: Icons.stop_circle_outlined,
            ),
            const SizedBox(height: EvSpace.md),
            Text(
              'Recorded $elapsed · ${controller.pauseCount} '
              '${controller.pauseCount == 1 ? 'pause' : 'pauses'}',
              style: textTheme.titleMedium?.copyWith(color: Colors.white),
              textAlign: TextAlign.center,
            ),
            if (controller.chunkPipeline case final pipeline?) ...[
              const SizedBox(height: EvSpace.md),
              _SaveResult(
                key: ValueKey(controller.sessionId),
                manifest: pipeline.manifest,
              ),
            ],
            if (onDone != null) ...[
              gap,
              OutlinedButton.icon(
                key: RecordingScreen.doneKey,
                onPressed: onDone,
                style: OutlinedButton.styleFrom(
                  shape: const StadiumBorder(),
                  minimumSize: const Size(160, 48),
                ),
                icon: const Icon(Icons.check_rounded),
                label: const Text('Done'),
              ),
            ],
          ],
        ),
      ),
    };
    // A short fade when the state changes (none with reduced motion).
    return _FadeIn(
      key: ValueKey((controller.state, controller.isStartingCapture)),
      child: view,
    );
  }
}

/// Fades its child in once, when it first appears (≤ 220 ms).
class _FadeIn extends StatelessWidget {
  const _FadeIn({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (EvMotion.reduced(context)) return child;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 220),
      curve: EvMotion.curve,
      builder: (context, t, child) => Opacity(opacity: t, child: child),
      child: child,
    );
  }
}

/// Idle: a white microphone on a dark core inside deep-red rings (as on
/// Home).
class _MicBadge extends StatelessWidget {
  const _MicBadge();

  @override
  Widget build(BuildContext context) {
    Widget ring(double size, Color fill, Color border, Widget child) =>
        Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: fill,
            border: Border.all(color: border),
          ),
          child: child,
        );
    return ExcludeSemantics(
      child: ring(
        132,
        EvEmber.red.withValues(alpha: 0.10),
        Colors.white.withValues(alpha: 0.06),
        ring(
          104,
          EvEmber.wine.withValues(alpha: 0.55),
          EvEmber.red.withValues(alpha: 0.35),
          Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: EvEmber.black,
              border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
              boxShadow: [
                BoxShadow(
                  color: EvEmber.accent.withValues(alpha: 0.28),
                  blurRadius: 26,
                ),
              ],
            ),
            child: const Icon(Icons.mic_rounded, size: 32, color: Colors.white),
          ),
        ),
      ),
    );
  }
}

/// After Stop: confirms the recording is stored on the phone only when the
/// save actually finished (the pipeline's manifest future), never before.
class _SaveResult extends StatelessWidget {
  const _SaveResult({super.key, required this.manifest});

  final Future<Map<String, Object?>> manifest;

  static const resultKey = Key('outbox-result');

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, Object?>>(
      future: manifest,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return const NoticeCard(
            key: resultKey,
            icon: Icons.error_outline_rounded,
            title: 'The recording could not be saved completely',
            message: 'Some audio may be missing. Try recording again.',
            tone: PillTone.danger,
          );
        }
        final m = snapshot.data;
        if (m == null) {
          return const StatusPill(
            key: resultKey,
            icon: Icons.hourglass_top_rounded,
            label: 'Saving…',
          );
        }
        final failed = (m['failed_chunks'] as List<Object?>?)?.length ?? 0;
        if (failed > 0) {
          return const NoticeCard(
            key: resultKey,
            icon: Icons.warning_amber_rounded,
            title: 'Saved, with gaps',
            message:
                'A few parts of this recording could not be saved. The rest '
                'is on this phone and will be sent to your PC.',
            tone: PillTone.warning,
          );
        }
        return const NoticeCard(
          key: resultKey,
          icon: Icons.check_circle_outline_rounded,
          title: 'Saved on this phone',
          message:
              'It will be sent to your PC over your local network. You can '
              'find it in Sessions.',
          tone: PillTone.positive,
        );
      },
    );
  }
}

/// Shown after Start/Resume until the first audio arrives: no red dot, so
/// the indicator never claims a recording before the microphone delivers.
class StartingIndicator extends StatelessWidget {
  const StartingIndicator({super.key, required this.elapsed});

  final String elapsed;

  static const label = 'Starting microphone…';

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    const color = EvEmber.textSoft;
    return Semantics(
      liveRegion: true,
      label: label,
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox.square(
                dimension: 14,
                child: CircularProgressIndicator(strokeWidth: 2, color: color),
              ),
              const SizedBox(width: 10),
              Flexible(
                child: Text(
                  label,
                  style: textTheme.titleSmall?.copyWith(color: color),
                ),
              ),
            ],
          ),
          const SizedBox(height: EvSpace.sm),
          Text(elapsed, style: _timerStyle(context, EvEmber.textFaint)),
        ],
      ),
    );
  }
}

/// The large, light elapsed-time figure.
TextStyle? _timerStyle(BuildContext context, Color color) =>
    Theme.of(context).textTheme.displayLarge?.copyWith(
      color: color,
      fontWeight: FontWeight.w200,
      fontSize: 64,
      letterSpacing: -1,
    );

/// While recording: whether speech is currently being heard.
class SpeechStatus extends StatelessWidget {
  const SpeechStatus({super.key, required this.speech});

  final bool speech;

  static const speechKey = Key('speech-detected');
  static const listeningKey = Key('listening');

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final color = speech ? EvEmber.accentSoft : EvEmber.textSoft;
    return Semantics(
      label: speech ? 'Speech detected' : 'Listening for speech',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            speech ? Icons.record_voice_over_rounded : Icons.hearing_rounded,
            color: color,
            size: 18,
          ),
          const SizedBox(width: EvSpace.xs),
          Flexible(
            child: Text(
              key: speech ? speechKey : listeningKey,
              speech ? 'Speech detected' : 'Listening for speech',
              style: textTheme.titleSmall?.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }
}

/// Shown only while recording (FR1): red dot, "Recording", elapsed timer.
class RecordingIndicator extends StatelessWidget {
  const RecordingIndicator({super.key, required this.elapsed});

  final String elapsed;

  static const dotKey = Key('recording-dot');
  static const timerKey = Key('recording-timer');

  @override
  Widget build(BuildContext context) {
    // Two nodes: the state is a live region (announced once when recording
    // starts or resumes); the timer is read on request, not every second.
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          label: 'Recorded time $elapsed',
          excludeSemantics: true,
          child: Text(
            key: timerKey,
            elapsed,
            style: _timerStyle(context, Colors.white),
          ),
        ),
        const SizedBox(height: EvSpace.xs),
        Semantics(
          liveRegion: true,
          label: 'Recording',
          excludeSemantics: true,
          child: GlassChip(
            large: true,
            leading: Container(
              key: dotKey,
              width: 10,
              height: 10,
              decoration: const BoxDecoration(
                color: Colors.red,
                shape: BoxShape.circle,
              ),
            ),
            label: 'Recording',
          ),
        ),
      ],
    );
  }
}

/// Distinct paused display: pause icon, "Paused", frozen elapsed time.
class PausedIndicator extends StatelessWidget {
  const PausedIndicator({super.key, required this.elapsed});

  final String elapsed;

  static const timerKey = Key('paused-timer');

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Semantics(
          label: 'Recorded time $elapsed',
          excludeSemantics: true,
          child: Text(
            key: timerKey,
            elapsed,
            style: _timerStyle(context, EvEmber.textSoft),
          ),
        ),
        const SizedBox(height: EvSpace.xs),
        Semantics(
          liveRegion: true,
          label: 'Paused. Nothing is being recorded.',
          excludeSemantics: true,
          child: const GlassChip(
            large: true,
            leading: Icon(
              Icons.pause_circle_filled,
              color: EvColors.warning,
              size: 18,
            ),
            label: 'Paused',
            color: EvColors.warning,
          ),
        ),
      ],
    );
  }
}

/// Shown while paused because the app left the foreground. Resume stays a
/// user action.
class AutoPauseNotice extends StatelessWidget {
  const AutoPauseNotice({super.key});

  static const title = 'Paused automatically';
  static const detail =
      'Echo Vault left the screen, so recording was paused. Nothing is '
      'recorded until you tap Resume.';

  @override
  Widget build(BuildContext context) {
    return const NoticeCard(
      key: Key('auto-pause-notice'),
      icon: Icons.info_outline_rounded,
      title: title,
      message: detail,
      tone: PillTone.warning,
    );
  }
}

class _PermissionMessage extends StatelessWidget {
  const _PermissionMessage({required this.message, this.onOpenSettings});

  final String message;

  /// Microphone blocked: a button to this app's page in Android Settings.
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return NoticeCard(
      key: const Key('permission-message'),
      icon: Icons.mic_off_rounded,
      message: message,
      tone: PillTone.danger,
      action: onOpenSettings == null
          ? null
          : Align(
              alignment: AlignmentDirectional.centerStart,
              child: OutlinedButton.icon(
                key: RecordingScreen.openSettingsKey,
                onPressed: onOpenSettings,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: EvEmber.glassBorder),
                  minimumSize: const Size(0, 48),
                ),
                icon: const Icon(Icons.settings_outlined, size: 18),
                label: const Text('Open app settings'),
              ),
            ),
    );
  }
}

class _PrivacyFootnote extends StatelessWidget {
  const _PrivacyFootnote();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        const Icon(
          Icons.lock_outline_rounded,
          size: 14,
          color: EvEmber.textFaint,
        ),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            'Audio is captured only while this screen shows Recording',
            textAlign: TextAlign.center,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
          ),
        ),
      ],
    );
  }
}

/// Round controls: one large Start when no session is open; a small
/// Pause/Resume and a large Stop while one is.
class _Controls extends StatelessWidget {
  const _Controls({
    required this.controller,
    required this.onStart,
    required this.onPauseResume,
    required this.onStop,
  });

  final RecordingController controller;

  /// The screen's wrappers around [controller]'s actions (haptics and the
  /// double-tap guard).
  final VoidCallback onStart;
  final VoidCallback onPauseResume;
  final VoidCallback onStop;

  static const startKey = Key('start-button');
  static const pauseResumeKey = Key('pause-resume-button');
  static const stopKey = Key('stop-button');

  static const double _large = 96;
  static const double _small = 72;

  @override
  Widget build(BuildContext context) {
    final state = controller.state;
    final open =
        state == SessionState.recording || state == SessionState.paused;
    if (!open) {
      // No session open: one clear Start action (a new session after Stop).
      return Center(
        child: _ControlButton(
          buttonKey: startKey,
          kind: _ButtonKind.primary,
          size: _large,
          onPressed: controller.canStart ? onStart : null,
          icon: Icons.mic_rounded,
          label: state == SessionState.stopped ? 'Record again' : 'Start',
        ),
      );
    }
    final paused = state == SessionState.paused;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _ControlButton(
          buttonKey: pauseResumeKey,
          kind: _ButtonKind.secondary,
          size: _small,
          onPressed: (paused ? controller.canResume : controller.canPause)
              ? onPauseResume
              : null,
          icon: paused ? Icons.play_arrow_rounded : Icons.pause_rounded,
          label: paused ? 'Resume' : 'Pause',
        ),
        // Generous gap so Stop is not pressed by mistake.
        const SizedBox(width: EvSpace.lg),
        _ControlButton(
          buttonKey: stopKey,
          kind: _ButtonKind.danger,
          size: _large,
          onPressed: controller.canStop ? onStop : null,
          icon: Icons.stop_rounded,
          label: 'Stop',
        ),
        // Balances the row so Stop sits in the centre.
        const SizedBox(width: EvSpace.lg + _small),
      ],
    );
  }
}

enum _ButtonKind { primary, secondary, danger }

/// Round glass button with an icon above a label that never wraps: the
/// label shrinks (rather than wraps) if it does not fit, e.g. at large text
/// scales.
class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.buttonKey,
    required this.icon,
    required this.label,
    required this.onPressed,
    required this.kind,
    required this.size,
  });

  /// Key for the underlying [ButtonStyleButton] (used by tests).
  final Key buttonKey;
  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final _ButtonKind kind;
  final double size;

  @override
  Widget build(BuildContext context) {
    final (background, foreground, border) = switch (kind) {
      _ButtonKind.primary => (Colors.white, EvEmber.black, Colors.white),
      _ButtonKind.secondary => (
        EvEmber.glassStrong,
        Colors.white,
        EvEmber.glassBorder,
      ),
      _ButtonKind.danger => (
        EvEmber.stop,
        Colors.white,
        const Color(0x66FFFFFF),
      ),
    };
    return FilledButton(
      key: buttonKey,
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        fixedSize: Size.square(size),
        minimumSize: Size.square(size),
        padding: const EdgeInsets.all(EvSpace.xs),
        shape: CircleBorder(side: BorderSide(color: border)),
        backgroundColor: background,
        foregroundColor: foreground,
        disabledBackgroundColor: EvEmber.glass,
        disabledForegroundColor: EvEmber.textFaint,
        elevation: kind == _ButtonKind.danger ? 6 : 0,
        shadowColor: EvEmber.accent.withValues(alpha: 0.6),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: size * 0.3),
          const SizedBox(height: 2),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              label,
              maxLines: 1,
              softWrap: false,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
