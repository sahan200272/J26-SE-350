import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'display_format.dart';
import 'processing_privacy_screen.dart';
import 'sessions_screen.dart';
import 'theme/app_theme.dart';

/// Home: a compact greeting, the microphone button that opens the recording
/// screen, and the three most recent recordings with a way to see them all.
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    this.sessions,
    this.syncthing,
    this.refreshToken = 0,
    this.onStartRecording,
    this.onOpenSessions,
    this.now = DateTime.now,
  });

  /// Recent recordings; the section is hidden when null.
  final SessionSource? sessions;

  /// Lets the recording page say whether the PC already has a recording.
  final SyncthingClient? syncthing;
  final int refreshToken;
  final VoidCallback? onStartRecording;
  final VoidCallback? onOpenSessions;
  final DateTime Function() now;

  static const startKey = Key('home-start-recording');
  static const recentKey = Key('home-recent');
  static const privacyKey = Key('home-privacy');

  /// How many recent recordings Home shows.
  static const recentCount = 3;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<SessionSummary>? _recent;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(HomeScreen old) {
    super.didUpdateWidget(old);
    if (old.refreshToken != widget.refreshToken) unawaited(_load());
  }

  Future<void> _load() async {
    final source = widget.sessions;
    if (source == null) return;
    try {
      final all = await source.list();
      if (!mounted) return;
      setState(() {
        _recent = all.take(HomeScreen.recentCount).toList();
        _failed = false;
      });
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    }
  }

  static String _greeting(DateTime now) => switch (now.hour) {
    < 5 => 'Good evening',
    < 12 => 'Good morning',
    < 17 => 'Good afternoon',
    _ => 'Good evening',
  };

  void _openPrivacy() => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => const ProcessingPrivacyScreen()),
  );

  Future<void> _open(SessionSummary s) async {
    await openSessionDetail(
      context,
      s,
      source: widget.sessions,
      syncthing: widget.syncthing,
    );
    if (mounted) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    const padding = EdgeInsets.fromLTRB(
      EvSpace.md,
      EvSpace.sm,
      EvSpace.md,
      EvSpace.md,
    );
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, box) => SingleChildScrollView(
            padding: padding,
            child: ConstrainedBox(
              // Fill the screen on tall phones (the microphone sits in the
              // middle); scroll on short ones or at large text sizes.
              constraints: BoxConstraints(
                minHeight: math.max(0.0, box.maxHeight - padding.vertical),
              ),
              child: IntrinsicHeight(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _HomeHeader(onOpenPrivacy: _openPrivacy),
                    const SizedBox(height: EvSpace.lg),
                    Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: EvSpace.xxs,
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _greeting(widget.now()),
                            style: textTheme.bodyLarge?.copyWith(
                              color: EvColors.textMuted,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            'Capture what matters',
                            style: textTheme.headlineSmall,
                          ),
                        ],
                      ),
                    ),
                    const Expanded(child: SizedBox(height: EvSpace.lg)),
                    _RecordHero(onTap: widget.onStartRecording),
                    const Expanded(child: SizedBox(height: EvSpace.lg)),
                    if (widget.sessions != null) _recentCard(context),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _recentCard(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final openAll = widget.onOpenSessions;
    return EvCard(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.md,
        EvSpace.xxs,
        EvSpace.xs,
        EvSpace.md,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Semantics(
                  button: openAll != null,
                  label: 'Recent recordings',
                  hint: openAll == null ? null : 'Opens all recordings',
                  excludeSemantics: true,
                  child: InkWell(
                    onTap: openAll,
                    borderRadius: BorderRadius.circular(EvRadius.sm),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        vertical: EvSpace.sm,
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.graphic_eq_rounded,
                            size: 18,
                            color: EvColors.teal,
                          ),
                          const SizedBox(width: EvSpace.xs),
                          Flexible(
                            child: Text(
                              'Recent recordings',
                              style: textTheme.titleSmall,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              if (openAll != null)
                TextButton(onPressed: openAll, child: const Text('See all')),
            ],
          ),
          const SizedBox(height: EvSpace.xs),
          Padding(
            padding: const EdgeInsets.only(right: EvSpace.xs),
            child: _recentBody(context),
          ),
        ],
      ),
    );
  }

  Widget _recentBody(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final recent = _recent;
    if (_failed && recent == null) {
      return Text(
        key: HomeScreen.recentKey,
        'Recent recordings could not be loaded.',
        style: textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
      );
    }
    if (recent == null) {
      return const _RecentRow(
        key: HomeScreen.recentKey,
        children: [_TileSkeleton(), _TileSkeleton(), _TileSkeleton()],
      );
    }
    if (recent.isEmpty) {
      return Row(
        key: HomeScreen.recentKey,
        children: [
          const IconBadge(
            Icons.mic_none_rounded,
            color: EvColors.textMuted,
            size: 40,
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Text(
              'No recordings yet. Tap the microphone to capture your first '
              'conversation.',
              style: textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
            ),
          ),
        ],
      );
    }
    final now = widget.now();
    return _RecentRow(
      key: HomeScreen.recentKey,
      children: [
        for (final s in recent)
          _RecentTile(session: s, now: now, onTap: () => _open(s)),
      ],
    );
  }
}

/// Brand on the left; on the right a small "Private" chip that opens
/// Processing & privacy.
class _HomeHeader extends StatelessWidget {
  const _HomeHeader({required this.onOpenPrivacy});

  final VoidCallback onOpenPrivacy;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Row(
      children: [
        const Expanded(
          child: Align(
            alignment: Alignment.centerLeft,
            child: BrandTitle(),
          ),
        ),
        const SizedBox(width: EvSpace.xs),
        Semantics(
          button: true,
          label: 'Private by design',
          hint: 'See how your recordings are handled',
          excludeSemantics: true,
          child: Material(
            key: HomeScreen.privacyKey,
            color: EvColors.surfaceLow,
            shape: const StadiumBorder(
              side: BorderSide(color: EvColors.border),
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onOpenPrivacy,
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: 40),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: EvSpace.sm),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.shield_outlined,
                        size: 16,
                        color: EvColors.teal,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Private',
                        style: textTheme.labelLarge?.copyWith(
                          color: EvColors.snow,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

/// The main action: a large microphone button between two static waveform
/// illustrations, with one short label.
class _RecordHero extends StatelessWidget {
  const _RecordHero({required this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final enabled = onTap != null;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          height: 148,
          child: Row(
            children: [
              const Expanded(child: _WaveIllustration()),
              const SizedBox(width: EvSpace.sm),
              _MicButton(onTap: onTap),
              const SizedBox(width: EvSpace.sm),
              const Expanded(child: _WaveIllustration(mirrored: true)),
            ],
          ),
        ),
        const SizedBox(height: EvSpace.md),
        Text(
          'Start recording',
          style: textTheme.titleMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: EvSpace.xxs),
        Text(
          enabled
              ? 'Your conversations, your control.'
              : 'Recording is not available right now.',
          style: textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class _MicButton extends StatelessWidget {
  const _MicButton({required this.onTap});

  final VoidCallback? onTap;

  static const double _core = 88;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    final accent = enabled ? EvColors.teal : EvColors.textSubtle;
    return Semantics(
      button: true,
      enabled: enabled,
      label: 'Start recording',
      excludeSemantics: true,
      child: Container(
        width: 148,
        height: 148,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: accent.withValues(alpha: 0.05),
          border: Border.all(color: accent.withValues(alpha: 0.10)),
        ),
        child: Container(
          width: 118,
          height: 118,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: accent.withValues(alpha: 0.09),
            border: Border.all(color: accent.withValues(alpha: 0.22)),
          ),
          child: DecoratedBox(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              boxShadow: enabled
                  ? [
                      BoxShadow(
                        color: EvColors.teal.withValues(alpha: 0.35),
                        blurRadius: 28,
                        spreadRadius: 1,
                      ),
                    ]
                  : null,
            ),
            child: Material(
              key: HomeScreen.startKey,
              shape: const CircleBorder(),
              clipBehavior: Clip.antiAlias,
              color: enabled ? EvColors.teal : EvColors.surfaceHigh,
              child: InkWell(
                onTap: onTap,
                child: SizedBox.square(
                  dimension: _core,
                  child: Icon(
                    Icons.mic_rounded,
                    size: 38,
                    color: enabled ? EvColors.navy : EvColors.textSubtle,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Static decorative bars beside the microphone. Purely an illustration: it
/// does not move and does not show live audio.
class _WaveIllustration extends StatelessWidget {
  const _WaveIllustration({this.mirrored = false});

  final bool mirrored;

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        height: 64,
        width: double.infinity,
        child: CustomPaint(painter: _WaveIllustrationPainter(mirrored)),
      ),
    );
  }
}

class _WaveIllustrationPainter extends CustomPainter {
  _WaveIllustrationPainter(this.mirrored);

  final bool mirrored;

  // Fixed bar heights (0..1); the last value is the bar nearest the
  // microphone.
  static const _heights = [
    0.18, 0.30, 0.22, 0.45, 0.32, 0.60, 0.40, 0.78, 0.52, 0.92, 0.66, 0.84, //
    0.48, 0.70, 0.36,
  ];

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0) return;
    const slot = 7.0;
    final count = math.min(_heights.length, (size.width / slot).floor());
    if (count <= 0) return;
    final mid = size.height / 2;
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3;
    for (var i = 0; i < count; i++) {
      // Index 0 is the bar nearest the microphone.
      final h = _heights[_heights.length - 1 - i];
      final half = math.max(1.5, h * (size.height / 2 - 2));
      final fromMic = slot * i + slot / 2;
      final x = mirrored ? fromMic : size.width - fromMic;
      final fade = count <= 1 ? 1.0 : 1 - i / (count - 1);
      paint.color = EvColors.textMuted.withValues(alpha: 0.12 + 0.38 * fade);
      canvas.drawLine(Offset(x, mid - half), Offset(x, mid + half), paint);
    }
  }

  @override
  bool shouldRepaint(_WaveIllustrationPainter old) => old.mirrored != mirrored;
}

/// Up to [HomeScreen.recentCount] equal-width tiles; empty slots keep the
/// widths the same when there are fewer recordings.
class _RecentRow extends StatelessWidget {
  const _RecentRow({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < HomeScreen.recentCount; i++) ...[
            if (i > 0) const SizedBox(width: EvSpace.xs),
            Expanded(
              child: i < children.length ? children[i] : const SizedBox(),
            ),
          ],
        ],
      ),
    );
  }
}

/// One recent recording: icon, title, length and day.
class _RecentTile extends StatelessWidget {
  const _RecentTile({
    required this.session,
    required this.now,
    required this.onTap,
  });

  final SessionSummary session;
  final DateTime now;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final s = session;
    final length = s.recordedMs ?? s.sessionEndMs;
    final meta = TextStyle(
      fontSize: textTheme.bodySmall?.fontSize,
      color: EvColors.textMuted,
      height: 1.3,
    );
    return Material(
      color: EvColors.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.md),
        side: const BorderSide(color: EvColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(EvSpace.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const IconBadge(Icons.graphic_eq_rounded, size: 32),
              const SizedBox(height: EvSpace.sm),
              Text(
                sessionTitle(s),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: textTheme.labelLarge?.copyWith(
                  color: EvColors.snow,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: EvSpace.xxs),
              Text(
                length == null ? '–' : formatSpan(length),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: meta.copyWith(
                  color: EvColors.teal,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (s.start != null)
                Text(
                  formatDay(s.start!, now),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: meta,
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TileSkeleton extends StatelessWidget {
  const _TileSkeleton();

  @override
  Widget build(BuildContext context) {
    Widget bar(double width, double height) => Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: EvColors.surfaceHigh,
        borderRadius: BorderRadius.circular(EvRadius.sm),
      ),
    );
    return ExcludeSemantics(
      child: Container(
        padding: const EdgeInsets.all(EvSpace.sm),
        decoration: BoxDecoration(
          color: EvColors.surface,
          borderRadius: BorderRadius.circular(EvRadius.md),
          border: Border.all(color: EvColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            bar(32, 32),
            const SizedBox(height: EvSpace.sm),
            bar(64, 10),
            const SizedBox(height: EvSpace.xs),
            bar(40, 10),
            const SizedBox(height: EvSpace.xs),
          ],
        ),
      ),
    );
  }
}
