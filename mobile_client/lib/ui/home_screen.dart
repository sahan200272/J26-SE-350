import 'dart:async';

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'processing_privacy_screen.dart';
import 'sessions_screen.dart';
import 'theme/app_theme.dart';

/// Home: welcome, the Start recording action, recent recordings and the
/// way into Knowledge and Assistant.
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    this.sessions,
    this.syncthing,
    this.refreshToken = 0,
    this.onStartRecording,
    this.onOpenSessions,
    this.onOpenKnowledge,
    this.onOpenAssistant,
    this.now = DateTime.now,
  });

  /// Recent recordings; the section is hidden when null.
  final SessionSource? sessions;

  /// Lets the recording page say whether the PC already has a recording.
  final SyncthingClient? syncthing;
  final int refreshToken;
  final VoidCallback? onStartRecording;
  final VoidCallback? onOpenSessions;
  final VoidCallback? onOpenKnowledge;
  final VoidCallback? onOpenAssistant;
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

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.md,
            EvSpace.md,
            EvSpace.xl,
          ),
          children: [
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: EvSpace.xxs),
              child: Row(children: [BrandTitle()]),
            ),
            const SizedBox(height: EvSpace.lg),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: EvSpace.xxs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _greeting(widget.now()),
                    style: textTheme.bodyLarge?.copyWith(
                      color: EvColors.textMuted,
                    ),
                  ),
                  const SizedBox(height: EvSpace.xxs),
                  Text(
                    'Capture what matters',
                    style: textTheme.headlineMedium,
                  ),
                  const SizedBox(height: EvSpace.xs),
                  Text(
                    'Echo Vault records conversations only when you choose, '
                    'and sends them to Echo Vault on your own computer, '
                    'never to the cloud.',
                    style: textTheme.bodyMedium?.copyWith(
                      color: EvColors.textMuted,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: EvSpace.lg),
            _StartRecordingCard(onTap: widget.onStartRecording),
            if (widget.sessions != null) ...[
              SectionTitle(
                'Recent recordings',
                actionLabel: 'See all',
                onAction: widget.onOpenSessions,
              ),
              _recentSection(context),
            ],
            const SectionTitle('Explore'),
            IntrinsicHeight(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    child: _FeatureTile(
                      icon: Icons.hub_outlined,
                      title: 'Knowledge',
                      subtitle: 'People, topics and how they connect',
                      onTap: widget.onOpenKnowledge,
                    ),
                  ),
                  const SizedBox(width: EvSpace.sm),
                  Expanded(
                    child: _FeatureTile(
                      icon: Icons.auto_awesome_outlined,
                      title: 'Assistant',
                      subtitle: 'Ask about past conversations',
                      onTap: widget.onOpenAssistant,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: EvSpace.lg),
            GroupCard(
              children: [
                InfoRow(
                  key: HomeScreen.privacyKey,
                  icon: Icons.shield_outlined,
                  title: 'Private by design',
                  subtitle: 'See how your recordings are handled',
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => const ProcessingPrivacyScreen(),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _open(SessionSummary s) async {
    await openSessionDetail(
      context,
      s,
      source: widget.sessions,
      syncthing: widget.syncthing,
    );
    if (mounted) await _load();
  }

  Widget _recentSection(BuildContext context) {
    final recent = _recent;
    if (_failed && recent == null) {
      return const EvCard(
        key: HomeScreen.recentKey,
        child: Text('Recent recordings could not be loaded.'),
      );
    }
    if (recent == null) {
      return const SkeletonCard(key: HomeScreen.recentKey);
    }
    if (recent.isEmpty) {
      return EvCard(
        key: HomeScreen.recentKey,
        child: Row(
          children: [
            const IconBadge(
              Icons.graphic_eq_rounded,
              color: EvColors.textMuted,
            ),
            const SizedBox(width: EvSpace.sm),
            Expanded(
              child: Text(
                'No recordings yet. Your first one will appear here.',
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
              ),
            ),
          ],
        ),
      );
    }
    final now = widget.now();
    return Column(
      key: HomeScreen.recentKey,
      children: [
        for (final (i, s) in recent.indexed) ...[
          if (i > 0) const SizedBox(height: EvSpace.sm),
          SessionTile(
            session: s,
            showDay: true,
            now: now,
            onTap: () => _open(s),
          ),
        ],
      ],
    );
  }
}

/// The primary action: large, high-contrast, with one clear label.
class _StartRecordingCard extends StatelessWidget {
  const _StartRecordingCard({required this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final enabled = onTap != null;
    return Semantics(
      button: true,
      enabled: enabled,
      label: 'Start recording',
      excludeSemantics: true,
      child: Material(
        key: HomeScreen.startKey,
        color: enabled ? EvColors.teal : EvColors.surfaceHigh,
        borderRadius: BorderRadius.circular(EvRadius.lg),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(EvSpace.lg),
            child: Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: EvColors.navy.withValues(alpha: enabled ? 1 : 0.4),
                  ),
                  child: Icon(
                    Icons.mic_rounded,
                    size: 28,
                    color: enabled ? EvColors.teal : EvColors.textSubtle,
                  ),
                ),
                const SizedBox(width: EvSpace.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Start recording',
                        style: textTheme.titleLarge?.copyWith(
                          color: enabled ? EvColors.navy : EvColors.textMuted,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        enabled
                            ? 'Begins right away. You stay in control.'
                            : 'Recording is not available right now.',
                        style: textTheme.bodyMedium?.copyWith(
                          color: enabled
                              ? EvColors.navy.withValues(alpha: 0.75)
                              : EvColors.textSubtle,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.arrow_forward_rounded,
                  color: enabled ? EvColors.navy : EvColors.textSubtle,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FeatureTile extends StatelessWidget {
  const _FeatureTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return EvCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconBadge(icon, color: EvColors.indigo, size: 40),
          const SizedBox(height: EvSpace.sm),
          Text(title, style: textTheme.titleMedium),
          const SizedBox(height: 2),
          Text(subtitle, style: textTheme.bodySmall),
          const SizedBox(height: EvSpace.sm),
          const StatusPill(label: 'Coming soon', tone: PillTone.indigo),
        ],
      ),
    );
  }
}
