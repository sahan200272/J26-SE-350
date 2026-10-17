import 'dart:math';

import 'package:flutter/material.dart';

import '../capture/audio_capture.dart';
import '../permissions/microphone_permission.dart';
import '../platform/app_channel.dart';
import '../session/clock.dart';
import '../session/recording_session.dart';
import 'elapsed_format.dart';
import 'input_level_meter.dart';
import 'lifecycle_source.dart';
import 'recording_controller.dart';

/// Main screen: status (idle / recording indicator with input level /
/// paused / stopped), messages and the Start, Pause/Resume and Stop buttons.
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
    this.debugFrameSinkFactory,
    this.debugSegmentSinkFactory,
    this.log,
  });

  final MicrophonePermission permission;
  final AudioCapture capture;
  final ScreenAwake screenAwake;
  final LifecycleSource lifecycle;
  final Clock? clock;
  final DateTime Function()? wallClock;
  final Random? random;
  final FrameSinkFactory? debugFrameSinkFactory;
  final SegmentSinkFactory? debugSegmentSinkFactory;
  final void Function(String message)? log;

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
    debugFrameSinkFactory: widget.debugFrameSinkFactory,
    debugSegmentSinkFactory: widget.debugSegmentSinkFactory,
    log: widget.log,
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Echo Vault')),
      body: SafeArea(
        child: ListenableBuilder(
          listenable: _controller,
          builder: (context, _) => Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: Center(child: _StatusView(controller: _controller)),
                ),
                if (_controller.message case final message?)
                  _PermissionMessage(message: message),
                const SizedBox(height: 16),
                _Controls(controller: _controller),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _StatusView extends StatelessWidget {
  const _StatusView({required this.controller});

  final RecordingController controller;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final elapsed = formatElapsed(controller.elapsed);
    return switch (controller.state) {
      SessionState.recording when controller.isStartingCapture =>
        StartingIndicator(elapsed: elapsed),
      SessionState.recording => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          RecordingIndicator(elapsed: elapsed),
          const SizedBox(height: 24),
          InputLevelMeter(dbfs: controller.inputLevelDbfs),
          const SizedBox(height: 16),
          SpeechStatus(
            speech: controller.isSpeechDetected,
            segments: controller.segmentCount,
          ),
        ],
      ),
      SessionState.paused => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          PausedIndicator(elapsed: elapsed),
          if (controller.pauseReason == PauseReason.autoBackground) ...[
            const SizedBox(height: 24),
            const AutoPauseNotice(),
          ],
        ],
      ),
      SessionState.idle => Text(
        controller.isRequestingPermission
            ? 'Requesting microphone access…'
            : 'Ready to record',
        style: textTheme.titleMedium,
      ),
      SessionState.stopped => Column(
        key: const Key('stopped-summary'),
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Stopped', style: textTheme.titleLarge),
          const SizedBox(height: 8),
          Text(
            'Recorded $elapsed · ${controller.pauseCount} '
            '${controller.pauseCount == 1 ? 'pause' : 'pauses'}',
            style: textTheme.bodyLarge,
          ),
          const SizedBox(height: 4),
          Text(
            key: const Key('segment-summary'),
            '${controller.segmentCount} speech '
            '${controller.segmentCount == 1 ? 'segment' : 'segments'}',
            style: textTheme.bodyMedium,
          ),
          if (controller.sessionId case final id?) ...[
            const SizedBox(height: 4),
            SelectableText(
              key: const Key('session-id'),
              'Session $id',
              style: textTheme.bodySmall,
            ),
          ],
        ],
      ),
    };
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
    final color = Theme.of(context).colorScheme.onSurfaceVariant;
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
              SizedBox.square(
                dimension: 16,
                child: CircularProgressIndicator(strokeWidth: 2, color: color),
              ),
              const SizedBox(width: 10),
              Flexible(
                child: Text(
                  label,
                  style: textTheme.titleLarge?.copyWith(color: color),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(elapsed, style: textTheme.displayMedium?.copyWith(color: color)),
        ],
      ),
    );
  }
}

/// While recording: whether the segmenter is inside speech, and how many
/// segments the session has so far.
class SpeechStatus extends StatelessWidget {
  const SpeechStatus({super.key, required this.speech, required this.segments});

  final bool speech;
  final int segments;

  static const speechKey = Key('speech-detected');
  static const listeningKey = Key('listening');
  static const countKey = Key('segment-count');

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final color = speech ? scheme.primary : scheme.onSurfaceVariant;
    return Semantics(
      label:
          '${speech ? 'Speech detected' : 'Listening for speech'}, '
          '$segments ${segments == 1 ? 'segment' : 'segments'}',
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                speech ? Icons.record_voice_over : Icons.hearing,
                color: color,
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  key: speech ? speechKey : listeningKey,
                  speech ? 'Speech detected' : 'Listening for speech',
                  style: textTheme.titleMedium?.copyWith(color: color),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            key: countKey,
            'Segments: $segments',
            style: textTheme.bodyMedium?.copyWith(
              color: scheme.onSurfaceVariant,
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
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                key: dotKey,
                width: 16,
                height: 16,
                decoration: const BoxDecoration(
                  color: Colors.red,
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 10),
              Text(
                'Recording',
                style: textTheme.titleLarge?.copyWith(color: Colors.red),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(key: timerKey, elapsed, style: textTheme.displayMedium),
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
    final color = Theme.of(context).colorScheme.onSurfaceVariant;
    return Semantics(
      liveRegion: true,
      label: 'Paused, $elapsed recorded',
      excludeSemantics: true,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.pause_circle_filled, color: color),
              const SizedBox(width: 8),
              Text(
                'Paused',
                style: textTheme.titleLarge?.copyWith(color: color),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            key: timerKey,
            elapsed,
            style: textTheme.displayMedium?.copyWith(color: color),
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
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Card(
      key: const Key('auto-pause-notice'),
      color: scheme.tertiaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(Icons.info_outline, color: scheme.onTertiaryContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: textTheme.titleMedium?.copyWith(
                      color: scheme.onTertiaryContainer,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    detail,
                    style: TextStyle(color: scheme.onTertiaryContainer),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PermissionMessage extends StatelessWidget {
  const _PermissionMessage({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      key: const Key('permission-message'),
      color: scheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(Icons.mic_off, color: scheme.onErrorContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message,
                style: TextStyle(color: scheme.onErrorContainer),
              ),
            ),
          ],
        ),
      ),
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
            filled: true,
            onPressed: controller.canStart ? controller.start : null,
            icon: Icons.mic,
            label: 'Start',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _ControlButton(
            buttonKey: pauseResumeKey,
            onPressed: paused
                ? (controller.canResume ? controller.resume : null)
                : (controller.canPause ? controller.pause : null),
            icon: paused ? Icons.play_arrow : Icons.pause,
            label: paused ? 'Resume' : 'Pause',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _ControlButton(
            buttonKey: stopKey,
            onPressed: controller.canStop ? controller.stop : null,
            icon: Icons.stop,
            label: 'Stop',
          ),
        ),
      ],
    );
  }
}

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
    this.filled = false,
  });

  /// Key for the underlying [ButtonStyleButton] (used by tests).
  final Key buttonKey;
  final IconData icon;
  final String label;
  final VoidCallback? onPressed;
  final bool filled;

  static const _style = ButtonStyle(
    padding: WidgetStatePropertyAll(
      EdgeInsets.symmetric(horizontal: 4, vertical: 12),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon),
        const SizedBox(height: 4),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(label, maxLines: 1, softWrap: false),
        ),
      ],
    );
    return filled
        ? FilledButton(
            key: buttonKey,
            style: _style,
            onPressed: onPressed,
            child: content,
          )
        : OutlinedButton(
            key: buttonKey,
            style: _style,
            onPressed: onPressed,
            child: content,
          );
  }
}
