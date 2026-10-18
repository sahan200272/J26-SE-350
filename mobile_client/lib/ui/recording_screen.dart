import 'dart:math';

import 'package:flutter/material.dart';

import '../capture/audio_capture.dart';
import '../permissions/microphone_permission.dart';
import '../platform/app_channel.dart';
import '../session/clock.dart';
import '../session/recording_session.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'elapsed_format.dart';
import 'input_level_meter.dart';
import 'lifecycle_source.dart';
import 'live_waveform.dart';
import 'recording_controller.dart';
import 'settings_screen.dart';
import 'theme/app_theme.dart';

/// Recording screen: status (ready / recording / paused / stopped), a large
/// timer, a live waveform of the microphone level, and the Start,
/// Pause/Resume and Stop buttons. Recording only ever starts from a user
/// action (Start here, or Start recording on Home, which opens this screen
/// with [autoStart]).
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
  });

  /// Opens the PC connection settings from the app bar; no button when null.
  final SyncthingClient? syncthing;
  final Future<String>? appVersion;

  static const settingsKey = Key('sync-settings-button');
  static const doneKey = Key('recording-done');

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
      if (_levels.isNotEmpty) _levels = const [];
    }

    final open = switch (state) {
      SessionState.recording || SessionState.paused => true,
      SessionState.idle || SessionState.stopped => false,
    };
    if (open != _sessionOpen) {
      _sessionOpen = open;
      widget.onSessionOpenChanged?.call(open);
      if (mounted) setState(() {}); // Updates PopScope.canPop.
    }
  }

  @override
  void dispose() {
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

  @override
  Widget build(BuildContext context) {
    final canLeave = Navigator.of(context).canPop();
    return PopScope(
      canPop: !_sessionOpen,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _blockedLeave();
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('New recording'),
          centerTitle: true,
          actions: [
            if (widget.syncthing case final syncthing?)
              ListenableBuilder(
                listenable: _controller,
                // Only between sessions: the recording indicator (FR1) must
                // stay on screen while a session is open.
                builder: (context, _) => IconButton(
                  key: RecordingScreen.settingsKey,
                  tooltip: 'Connect to your PC',
                  icon: const Icon(Icons.sync_rounded),
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
            const SizedBox(width: EvSpace.xxs),
          ],
        ),
        body: SafeArea(
          child: ListenableBuilder(
            listenable: _controller,
            builder: (context, _) => Padding(
              padding: const EdgeInsets.fromLTRB(
                EvSpace.lg,
                0,
                EvSpace.lg,
                EvSpace.md,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
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
                  if (_controller.message case final message?) ...[
                    _PermissionMessage(message: message),
                    const SizedBox(height: EvSpace.sm),
                  ],
                  _Controls(controller: _controller),
                  const SizedBox(height: EvSpace.sm),
                  const _PrivacyFootnote(),
                ],
              ),
            ),
          ),
        ),
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

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final muted = textTheme.bodyMedium?.copyWith(color: EvColors.textMuted);
    final elapsed = formatElapsed(controller.elapsed);
    const gap = SizedBox(height: EvSpace.lg);
    return switch (controller.state) {
      SessionState.recording when controller.isStartingCapture => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          StartingIndicator(elapsed: elapsed),
          gap,
          const LiveWaveform(levels: [], active: false),
        ],
      ),
      SessionState.recording => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          RecordingIndicator(elapsed: elapsed),
          gap,
          LiveWaveform(
            levels: levels,
            color: controller.isSpeechDetected
                ? EvColors.teal
                : EvColors.textMuted,
          ),
          const SizedBox(height: EvSpace.md),
          SpeechStatus(speech: controller.isSpeechDetected),
        ],
      ),
      SessionState.paused => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          PausedIndicator(elapsed: elapsed),
          gap,
          LiveWaveform(levels: levels, active: false),
          if (controller.pauseReason == PauseReason.autoBackground) ...[
            gap,
            const AutoPauseNotice(),
          ] else ...[
            const SizedBox(height: EvSpace.md),
            Text(
              'Nothing is being recorded while paused.',
              style: muted,
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
      SessionState.idle => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const _MicBadge(),
          gap,
          Text(
            controller.isRequestingPermission
                ? 'Requesting microphone access…'
                : 'Ready to record',
            style: textTheme.headlineSmall,
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
      SessionState.stopped => Column(
        key: const Key('stopped-summary'),
        mainAxisSize: MainAxisSize.min,
        children: [
          const StatusPill(label: 'Stopped', icon: Icons.stop_circle_outlined),
          const SizedBox(height: EvSpace.md),
          Text(
            'Recorded $elapsed · ${controller.pauseCount} '
            '${controller.pauseCount == 1 ? 'pause' : 'pauses'}',
            style: textTheme.titleMedium,
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
            TextButton.icon(
              key: RecordingScreen.doneKey,
              onPressed: onDone,
              icon: const Icon(Icons.check_rounded),
              label: const Text('Done'),
            ),
          ],
        ],
      ),
    };
  }
}

class _MicBadge extends StatelessWidget {
  const _MicBadge();

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: Container(
        width: 112,
        height: 112,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: EvColors.teal.withValues(alpha: 0.08),
          border: Border.all(color: EvColors.teal.withValues(alpha: 0.35)),
        ),
        child: const Icon(
          Icons.mic_none_rounded,
          size: 44,
          color: EvColors.teal,
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
    const color = EvColors.textMuted;
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
          Text(elapsed, style: textTheme.displayLarge?.copyWith(color: color)),
        ],
      ),
    );
  }
}

/// While recording: whether speech is currently being heard.
class SpeechStatus extends StatelessWidget {
  const SpeechStatus({super.key, required this.speech});

  final bool speech;

  static const speechKey = Key('speech-detected');
  static const listeningKey = Key('listening');

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final color = speech ? EvColors.teal : EvColors.textMuted;
    return Semantics(
      label: speech ? 'Speech detected' : 'Listening for speech',
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            speech ? Icons.record_voice_over_rounded : Icons.hearing_rounded,
            color: color,
            size: 20,
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
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      liveRegion: true,
      label: 'Recording, $elapsed',
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(
              color: EvColors.recording.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(EvRadius.pill),
              border: Border.all(
                color: EvColors.recording.withValues(alpha: 0.35),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  key: dotKey,
                  width: 10,
                  height: 10,
                  decoration: const BoxDecoration(
                    color: Colors.red,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  'Recording',
                  style: textTheme.titleSmall?.copyWith(
                    color: EvColors.recording,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: EvSpace.sm),
          Text(key: timerKey, elapsed, style: textTheme.displayLarge),
        ],
      ),
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
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      liveRegion: true,
      label: 'Paused, $elapsed recorded',
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
            decoration: BoxDecoration(
              color: EvColors.warning.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(EvRadius.pill),
              border: Border.all(
                color: EvColors.warning.withValues(alpha: 0.30),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.pause_circle_filled,
                  color: EvColors.warning,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Text(
                  'Paused',
                  style: textTheme.titleSmall?.copyWith(
                    color: EvColors.warning,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: EvSpace.sm),
          Text(
            key: timerKey,
            elapsed,
            style: textTheme.displayLarge?.copyWith(color: EvColors.textMuted),
          ),
        ],
      ),
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
  const _PermissionMessage({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return NoticeCard(
      key: const Key('permission-message'),
      icon: Icons.mic_off_rounded,
      message: message,
      tone: PillTone.danger,
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
          color: EvColors.textSubtle,
        ),
        const SizedBox(width: 6),
        Flexible(
          child: Text(
            'Audio is captured only while this screen shows Recording',
            textAlign: TextAlign.center,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: EvColors.textSubtle),
          ),
        ),
      ],
    );
  }
}

class _Controls extends StatelessWidget {
  const _Controls({required this.controller});

  final RecordingController controller;

  static const startKey = Key('start-button');
  static const pauseResumeKey = Key('pause-resume-button');
  static const stopKey = Key('stop-button');

  @override
  Widget build(BuildContext context) {
    final paused = controller.state == SessionState.paused;
    return Row(
      children: [
        Expanded(
          child: _ControlButton(
            buttonKey: startKey,
            kind: _ButtonKind.primary,
            onPressed: controller.canStart ? controller.start : null,
            icon: Icons.mic_rounded,
            label: 'Start',
          ),
        ),
        const SizedBox(width: EvSpace.sm),
        Expanded(
          child: _ControlButton(
            buttonKey: pauseResumeKey,
            kind: _ButtonKind.secondary,
            onPressed: paused
                ? (controller.canResume ? controller.resume : null)
                : (controller.canPause ? controller.pause : null),
            icon: paused ? Icons.play_arrow_rounded : Icons.pause_rounded,
            label: paused ? 'Resume' : 'Pause',
          ),
        ),
        const SizedBox(width: EvSpace.sm),
        Expanded(
          child: _ControlButton(
            buttonKey: stopKey,
            kind: _ButtonKind.danger,
            onPressed: controller.canStop ? controller.stop : null,
            icon: Icons.stop_rounded,
            label: 'Stop',
          ),
        ),
      ],
    );
  }
}

enum _ButtonKind { primary, secondary, danger }

/// Button with the icon above a label that never wraps: three buttons share
/// a narrow phone width, so the label gets the full button width, and
/// shrinks (rather than wraps) if it still does not fit, e.g. at large text
/// scales.
class _ControlButton extends StatelessWidget {
  const _ControlButton({
    required this.buttonKey,
    required this.icon,
    required this.label,
    required this.onPressed,
    required this.kind,
  });

  /// Key for the underlying [ButtonStyleButton] (used by tests).
  final Key buttonKey;
  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final _ButtonKind kind;

  static const _padding = EdgeInsets.symmetric(horizontal: 4, vertical: 12);
  static const _minSize = Size(64, 68);

  @override
  Widget build(BuildContext context) {
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 26),
        const SizedBox(height: 4),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(label, maxLines: 1, softWrap: false),
        ),
      ],
    );
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(EvRadius.lg),
    );
    return switch (kind) {
      _ButtonKind.primary => FilledButton(
        key: buttonKey,
        style: FilledButton.styleFrom(
          padding: _padding,
          minimumSize: _minSize,
          shape: shape,
        ),
        onPressed: onPressed,
        child: content,
      ),
      _ButtonKind.secondary => FilledButton.tonal(
        key: buttonKey,
        style: FilledButton.styleFrom(
          padding: _padding,
          minimumSize: _minSize,
          shape: shape,
          backgroundColor: EvColors.surfaceHigh,
          foregroundColor: EvColors.snow,
        ),
        onPressed: onPressed,
        child: content,
      ),
      _ButtonKind.danger => FilledButton.tonal(
        key: buttonKey,
        style: FilledButton.styleFrom(
          padding: _padding,
          minimumSize: _minSize,
          shape: shape,
          backgroundColor: EvColors.recording.withValues(alpha: 0.16),
          foregroundColor: EvColors.recording,
        ),
        onPressed: onPressed,
        child: content,
      ),
    };
  }
}
