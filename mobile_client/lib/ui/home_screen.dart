import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'display_format.dart';
import 'immersive_backdrop.dart';
import 'processing_privacy_screen.dart';
import 'sessions_screen.dart';
import 'theme/app_theme.dart';

/// Home: a compact greeting, the microphone button that opens the recording
/// screen, and the three most recent recordings with a way to see them all.
///
/// Visual layers, back to front: the background video
/// ([kBackgroundVideo], when present) or photo ([kBackgroundImage]), a
/// blurred dark "glass" layer that blends it into black and deep red, then
/// the content on frosted-glass cards ([ImmersiveBackdrop]).
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    this.sessions,
    this.syncthing,
    this.refreshToken = 0,
    this.onStartRecording,
    this.onOpenSessions,
    this.now = DateTime.now,
    this.isVisible = true,
  });

  /// Recent recordings; the section is hidden when null.
  final SessionSource? sessions;

  /// Lets the recording page say whether the PC already has a recording.
  final SyncthingClient? syncthing;
  final int refreshToken;
  final VoidCallback? onStartRecording;
  final VoidCallback? onOpenSessions;
  final DateTime Function() now;

  /// Home is the selected tab: the background video plays only then.
  final bool isVisible;

  static const startKey = Key('home-start-recording');
  static const recentKey = Key('home-recent');
  static const privacyKey = Key('home-privacy');
  static const backgroundKey = ImmersiveBackdrop.imageKey;

  /// How many recent recordings Home shows.
  static const recentCount = 3;

  /// The background photo. Replace this file to change it (portrait,
  /// about 1080 × 1920 or larger works best).
  static const backgroundAsset = kBackgroundImage;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

/// Home's dark, deep-red palette.
abstract final class _Ember {
  static const black = Color(0xFF070304);
  static const deep = Color(0xFF160606);
  static const wine = Color(0xFF3A0D0D);
  static const red = Color(0xFF8E1B16);
  static const accent = Color(0xFFFF4A3D);
  static const accentSoft = Color(0xFFFF8A7C);
  static const textSoft = Color(0xB8FFFFFF); // 72 % white
  static const textFaint = Color(0x85FFFFFF); // 52 % white
  static const glass = Color(0x14FFFFFF); // 8 % white
  static const glassStrong = Color(0x1FFFFFFF); // 12 % white
  static const glassBorder = Color(0x26FFFFFF); // 15 % white
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
    // The navigation bar floats over Home (the photo runs behind it); keep
    // the content clear of it.
    final padding = EdgeInsets.fromLTRB(
      EvSpace.md,
      EvSpace.sm,
      EvSpace.md,
      EvSpace.md + MediaQuery.paddingOf(context).bottom,
    );
    return Scaffold(
      backgroundColor: _Ember.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          ImmersiveBackdrop(
            videoAsset: kBackgroundVideo,
            playing: widget.isVisible,
          ),
          SafeArea(
            bottom: false,
            child: LayoutBuilder(
              builder: (context, box) => SingleChildScrollView(
                padding: padding,
                child: ConstrainedBox(
                  // Fill the screen on tall phones (the microphone sits in
                  // the middle); scroll on short ones or at large text.
                  constraints: BoxConstraints(
                    minHeight: math.max(0.0, box.maxHeight - padding.vertical),
                  ),
                  child: IntrinsicHeight(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _HomeHeader(onOpenPrivacy: _openPrivacy),
                        const SizedBox(height: EvSpace.xl),
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
                                  color: _Ember.textSoft,
                                ),
                              ),
                              const SizedBox(height: EvSpace.xxs),
                              Text.rich(
                                const TextSpan(
                                  text: 'Capture what ',
                                  children: [
                                    TextSpan(
                                      text: 'matters',
                                      style: TextStyle(
                                        color: _Ember.accent,
                                        decoration: TextDecoration.underline,
                                        decorationColor: _Ember.accent,
                                        decorationThickness: 2,
                                      ),
                                    ),
                                  ],
                                ),
                                style: textTheme.headlineMedium?.copyWith(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                  height: 1.15,
                                ),
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
        ],
      ),
    );
  }

  Widget _recentCard(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final openAll = widget.onOpenSessions;
    return _Glass(
      radius: 24,
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
                            color: _Ember.accent,
                          ),
                          const SizedBox(width: EvSpace.xs),
                          Flexible(
                            child: Text(
                              'Recent recordings',
                              style: textTheme.titleSmall?.copyWith(
                                color: Colors.white,
                              ),
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
                TextButton(
                  onPressed: openAll,
                  style: TextButton.styleFrom(
                    foregroundColor: _Ember.accentSoft,
                  ),
                  child: const Text('See all'),
                ),
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
        style: textTheme.bodyMedium?.copyWith(color: _Ember.textSoft),
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
          Container(
            width: 40,
            height: 40,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: _Ember.glassStrong,
            ),
            child: const Icon(
              Icons.mic_none_rounded,
              size: 20,
              color: _Ember.textSoft,
            ),
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Text(
              'No recordings yet. Tap the microphone to capture your first '
              'conversation.',
              style: textTheme.bodyMedium?.copyWith(color: _Ember.textSoft),
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

/// A frosted-glass surface: blurs what is behind it, with a faint white
/// fill and a hairline border.
class _Glass extends StatelessWidget {
  const _Glass({
    required this.child,
    this.radius = 20,
    this.padding = const EdgeInsets.all(EvSpace.md),
  });

  final Widget child;
  final double radius;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final shape = BorderRadius.circular(radius);
    return ClipRRect(
      borderRadius: shape,
      child: BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: 18, sigmaY: 18),
        child: Material(
          color: _Ember.glass,
          shape: RoundedRectangleBorder(
            borderRadius: shape,
            side: const BorderSide(color: _Ember.glassBorder),
          ),
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}

/// Brand on the left; on the right a small glass "Private" chip that opens
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
            color: _Ember.glass,
            shape: const StadiumBorder(
              side: BorderSide(color: _Ember.glassBorder),
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
                        color: Colors.white,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Private',
                        style: textTheme.labelLarge?.copyWith(
                          color: Colors.white,
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
          height: _MicButton.size,
          child: Row(
            children: [
              const Expanded(child: _WaveIllustration()),
              const SizedBox(width: EvSpace.xs),
              _MicButton(onTap: onTap),
              const SizedBox(width: EvSpace.xs),
              const Expanded(child: _WaveIllustration(mirrored: true)),
            ],
          ),
        ),
        const SizedBox(height: EvSpace.md),
        Text(
          'Start recording',
          style: textTheme.titleMedium?.copyWith(color: Colors.white),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: EvSpace.xxs),
        Text(
          enabled
              ? 'Your conversations, your control.'
              : 'Recording is not available right now.',
          style: textTheme.bodyMedium?.copyWith(color: _Ember.textSoft),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

/// White microphone on a near-black core, inside dark and deep-red rings.
class _MicButton extends StatelessWidget {
  const _MicButton({required this.onTap});

  final VoidCallback? onTap;

  static const double size = 168;
  static const double _core = 84;

  @override
  Widget build(BuildContext context) {
    final enabled = onTap != null;
    Widget ring(double diameter, Color fill, Color border, Widget child) =>
        Container(
          width: diameter,
          height: diameter,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: fill,
            border: Border.all(color: border),
          ),
          child: child,
        );
    return Semantics(
      button: true,
      enabled: enabled,
      label: 'Start recording',
      excludeSemantics: true,
      child: ring(
        size,
        _Ember.red.withValues(alpha: enabled ? 0.10 : 0.05),
        Colors.white.withValues(alpha: 0.06),
        ring(
          138,
          _Ember.wine.withValues(alpha: enabled ? 0.55 : 0.3),
          _Ember.red.withValues(alpha: 0.35),
          ring(
            110,
            _Ember.deep.withValues(alpha: 0.85),
            _Ember.red.withValues(alpha: 0.45),
            DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: enabled
                    ? [
                        BoxShadow(
                          color: _Ember.accent.withValues(alpha: 0.30),
                          blurRadius: 30,
                          spreadRadius: 2,
                        ),
                      ]
                    : null,
              ),
              child: Material(
                key: HomeScreen.startKey,
                shape: CircleBorder(
                  side: BorderSide(
                    color: Colors.white.withValues(alpha: 0.12),
                  ),
                ),
                clipBehavior: Clip.antiAlias,
                color: _Ember.black,
                child: InkWell(
                  onTap: onTap,
                  splashColor: _Ember.accent.withValues(alpha: 0.25),
                  child: SizedBox.square(
                    dimension: _core,
                    child: Icon(
                      Icons.mic_rounded,
                      size: 38,
                      color: enabled ? Colors.white : _Ember.textFaint,
                    ),
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
      paint.color = Colors.white.withValues(alpha: 0.08 + 0.42 * fade);
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
      color: _Ember.textFaint,
      height: 1.3,
    );
    return Material(
      color: _Ember.glass,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.md),
        side: const BorderSide(color: _Ember.glassBorder),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        splashColor: _Ember.accent.withValues(alpha: 0.18),
        child: Padding(
          padding: const EdgeInsets.all(EvSpace.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _Ember.accent.withValues(alpha: 0.16),
                ),
                child: const Icon(
                  Icons.graphic_eq_rounded,
                  size: 16,
                  color: _Ember.accentSoft,
                ),
              ),
              const SizedBox(height: EvSpace.sm),
              Text(
                sessionTitle(s),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: textTheme.labelLarge?.copyWith(
                  color: Colors.white,
                  height: 1.25,
                ),
              ),
              const SizedBox(height: EvSpace.xxs),
              Text(
                length == null ? '–' : formatSpan(length),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: meta.copyWith(
                  color: _Ember.accentSoft,
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
        color: _Ember.glassStrong,
        borderRadius: BorderRadius.circular(EvRadius.sm),
      ),
    );
    return ExcludeSemantics(
      child: Container(
        padding: const EdgeInsets.all(EvSpace.sm),
        decoration: BoxDecoration(
          color: _Ember.glass,
          borderRadius: BorderRadius.circular(EvRadius.md),
          border: Border.all(color: _Ember.glassBorder),
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
