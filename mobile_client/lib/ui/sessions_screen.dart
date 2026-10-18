import 'dart:async';

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import '../sync/syncthing_status.dart';
import 'components.dart';
import 'display_format.dart';
import 'pc_link_card.dart';
import 'session_detail_screen.dart';
import 'settings_screen.dart';
import 'theme/app_theme.dart';

/// Recordings stored on this phone, newest first. Reloads when
/// [refreshToken] changes and on pull-to-refresh.
class SessionsScreen extends StatefulWidget {
  const SessionsScreen({
    super.key,
    required this.source,
    this.syncthing,
    this.appVersion,
    this.refreshToken = 0,
    this.now = DateTime.now,
    this.onStartRecording,
  });

  final SessionSource source;
  final SyncthingClient? syncthing;
  final Future<String>? appVersion;
  final int refreshToken;
  final DateTime Function() now;

  /// Opens the recording screen (empty-state action); hidden when null.
  final VoidCallback? onStartRecording;

  static const listKey = Key('sessions-list');
  static const emptyKey = Key('sessions-empty');
  static const errorKey = Key('sessions-error');
  static const loadingKey = Key('sessions-loading');
  static const searchKey = Key('sessions-search');
  static const noMatchKey = Key('sessions-no-match');

  @override
  State<SessionsScreen> createState() => _SessionsScreenState();
}

class _SessionsScreenState extends State<SessionsScreen> {
  List<SessionSummary>? _sessions;
  bool _failed = false;
  SyncthingStatus? _sync;
  bool _loading = false;
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(SessionsScreen old) {
    super.didUpdateWidget(old);
    if (old.refreshToken != widget.refreshToken) unawaited(_load());
  }

  Future<void> _load() async {
    if (_loading) return;
    _loading = true;
    try {
      final sessions = await widget.source.list();
      SyncthingStatus? sync;
      if (widget.syncthing case final client?) {
        try {
          sync = await client.status();
        } catch (_) {
          sync = null;
        }
      }
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
        _sync = sync;
        _failed = false;
      });
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    } finally {
      _loading = false;
    }
  }

  void _openPairing() {
    final client = widget.syncthing;
    if (client == null) return;
    unawaited(
      Navigator.of(context)
          .push(
            MaterialPageRoute<void>(
              builder: (_) => SettingsScreen(
                syncthing: client,
                appVersion: widget.appVersion,
              ),
            ),
          )
          .then((_) => _load()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final sessions = _sessions;
    return Scaffold(
      appBar: AppBar(title: const Text('Sessions'), centerTitle: false),
      body: SafeArea(
        child: RefreshIndicator(
          color: EvColors.teal,
          backgroundColor: EvColors.surface,
          onRefresh: _load,
          child: ListView(
            key: SessionsScreen.listKey,
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(
              EvSpace.md,
              EvSpace.xs,
              EvSpace.md,
              EvSpace.xl,
            ),
            children: [
              if (widget.syncthing != null && sessions != null)
                PcLinkCard(status: _sync, onTap: _openPairing),
              if (_failed && sessions == null)
                EmptyState(
                  key: SessionsScreen.errorKey,
                  icon: Icons.error_outline_rounded,
                  title: 'Recordings could not be loaded',
                  message: 'Something went wrong reading this phone’s '
                      'storage. Pull down or try again.',
                  action: OutlinedButton.icon(
                    onPressed: _load,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Try again'),
                  ),
                )
              else if (sessions == null)
                const Column(
                  key: SessionsScreen.loadingKey,
                  children: [
                    SizedBox(height: EvSpace.md),
                    SkeletonCard(),
                    SizedBox(height: EvSpace.sm),
                    SkeletonCard(),
                    SizedBox(height: EvSpace.sm),
                    SkeletonCard(),
                  ],
                )
              else if (sessions.isEmpty)
                EmptyState(
                  key: SessionsScreen.emptyKey,
                  icon: Icons.graphic_eq_rounded,
                  title: 'No recordings yet',
                  message:
                      'Conversations you record appear here, ready to be '
                      'sent to your PC.',
                  action: widget.onStartRecording == null
                      ? null
                      : FilledButton.icon(
                          onPressed: widget.onStartRecording,
                          icon: const Icon(Icons.mic_rounded),
                          label: const Text('Start recording'),
                        ),
                )
              else
                ..._grouped(sessions),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _open(SessionSummary s) async {
    await openSessionDetail(
      context,
      s,
      source: widget.source,
      syncthing: widget.syncthing,
    );
    // Renamed or deleted: show the stored state.
    if (mounted) await _load();
  }

  /// Sessions whose title or day matches the search text.
  List<SessionSummary> _filter(List<SessionSummary> sessions) {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return sessions;
    final now = widget.now();
    return [
      for (final s in sessions)
        if (sessionTitle(s).toLowerCase().contains(q) ||
            (s.start != null &&
                formatDay(s.start!, now).toLowerCase().contains(q)))
          s,
    ];
  }

  List<Widget> _grouped(List<SessionSummary> all) {
    final now = widget.now();
    final widgets = <Widget>[
      if (all.length > 1) ...[
        const SizedBox(height: EvSpace.sm),
        _SearchField(
          controller: _search,
          onChanged: (value) => setState(() => _query = value),
        ),
      ],
    ];
    final sessions = _filter(all);
    if (sessions.isEmpty) {
      widgets.add(
        const EmptyState(
          key: SessionsScreen.noMatchKey,
          icon: Icons.search_off_rounded,
          title: 'No matching recordings',
          message: 'Try a different name or day.',
        ),
      );
      return widgets;
    }
    String? currentDay;
    for (final s in sessions) {
      final day = s.start == null ? 'Unknown date' : formatDay(s.start!, now);
      if (day != currentDay) {
        currentDay = day;
        widgets.add(SectionLabel(day));
      } else {
        widgets.add(const SizedBox(height: EvSpace.sm));
      }
      widgets.add(
        SessionTile(
          session: s,
          onTap: () => _open(s),
        ),
      );
    }
    return widgets;
  }
}

/// Opens [session] in the detail screen. Completes when it is closed (true
/// if the recording was deleted), so the caller can reload.
Future<bool> openSessionDetail(
  BuildContext context,
  SessionSummary session, {
  SessionSource? source,
  SyncthingClient? syncthing,
}) async {
  final deleted = await Navigator.of(context).push<bool>(
    MaterialPageRoute<bool>(
      builder: (_) => SessionDetailScreen(
        session: session,
        source: source,
        syncthing: syncthing,
      ),
    ),
  );
  return deleted ?? false;
}

/// The user's title, else `Recording at 14:05` (or `Recording` when the
/// time is unknown).
String sessionTitle(SessionSummary s) =>
    s.title ??
    (s.start == null ? 'Recording' : 'Recording at ${formatClock(s.start!)}');

/// One recording in a list: time, length, status, speech activity and
/// whether a transcript is available.
class SessionTile extends StatelessWidget {
  const SessionTile({
    super.key,
    required this.session,
    this.onTap,
    this.showDay = false,
    this.now,
  });

  final SessionSummary session;
  final VoidCallback? onTap;

  /// Prefix the length with the day (for lists not grouped by day).
  final bool showDay;
  final DateTime? now;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final s = session;
    final length = s.recordedMs ?? s.sessionEndMs;
    final details = [
      if (showDay && s.start != null)
        formatDay(s.start!, now ?? DateTime.now()),
      if (length != null) formatSpan(length),
      if (s.pauseCount > 0) plural(s.pauseCount, 'pause'),
    ].join(' · ');
    return EvCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const IconBadge(Icons.graphic_eq_rounded, size: 40),
              const SizedBox(width: EvSpace.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sessionTitle(s),
                      style: textTheme.titleMedium,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    if (details.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(details, style: textTheme.bodySmall),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: EvSpace.xs),
              SessionStatusPill(session: s),
            ],
          ),
          if (s.chunks.isNotEmpty && s.timelineMs > 0) ...[
            const SizedBox(height: EvSpace.md),
            SessionTimeline(session: s, height: 6),
          ],
          const SizedBox(height: EvSpace.sm),
          const TranscriptAvailability(),
        ],
      ),
    );
  }
}

/// One line saying whether a transcript can be shown. Transcripts are made
/// on the PC and are never sent back to the phone in this version.
class TranscriptAvailability extends StatelessWidget {
  const TranscriptAvailability({super.key});

  static const label = 'Transcript not available on this phone yet';

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Icon(Icons.notes_rounded, size: 16, color: EvColors.textSubtle),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: EvColors.textSubtle),
          ),
        ),
      ],
    );
  }
}

/// Filters the list by recording name or day.
class _SearchField extends StatelessWidget {
  const _SearchField({required this.controller, required this.onChanged});

  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return TextField(
      key: SessionsScreen.searchKey,
      controller: controller,
      onChanged: onChanged,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        hintText: 'Search recordings',
        prefixIcon: const Icon(Icons.search_rounded),
        suffixIcon: ListenableBuilder(
          listenable: controller,
          builder: (context, _) => controller.text.isEmpty
              ? const SizedBox.shrink()
              : IconButton(
                  tooltip: 'Clear search',
                  icon: const Icon(Icons.close_rounded),
                  onPressed: () {
                    controller.clear();
                    onChanged('');
                  },
                ),
        ),
        filled: true,
        fillColor: EvColors.surfaceLow,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(vertical: EvSpace.sm),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(EvRadius.pill),
          borderSide: const BorderSide(color: EvColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(EvRadius.pill),
          borderSide: const BorderSide(color: EvColors.border),
        ),
      ),
    );
  }
}

/// Saved, saved with gaps, incomplete, or cannot be opened.
class SessionStatusPill extends StatelessWidget {
  const SessionStatusPill({super.key, required this.session});

  final SessionSummary session;

  @override
  Widget build(BuildContext context) {
    if (session.error != null) {
      return const StatusPill(
        label: 'Can’t open',
        icon: Icons.error_outline_rounded,
        tone: PillTone.danger,
      );
    }
    if (!session.complete) {
      return const StatusPill(
        label: 'Incomplete',
        icon: Icons.hourglass_bottom_rounded,
        tone: PillTone.warning,
      );
    }
    if (session.failedChunks > 0) {
      return const StatusPill(
        label: 'Saved with gaps',
        icon: Icons.warning_amber_rounded,
        tone: PillTone.warning,
      );
    }
    return const StatusPill(
      label: 'Saved',
      icon: Icons.check_rounded,
      tone: PillTone.positive,
    );
  }
}

/// The recording as a track, with the moments where speech was heard
/// drawn at their positions.
class SessionTimeline extends StatelessWidget {
  const SessionTimeline({super.key, required this.session, this.height = 8});

  final SessionSummary session;
  final double height;

  @override
  Widget build(BuildContext context) {
    final total = session.timelineMs;
    return Semantics(
      label: 'Speech activity across ${formatSpan(total)}',
      excludeSemantics: true,
      child: LayoutBuilder(
        builder: (context, box) {
          final width = box.maxWidth;
          return ClipRRect(
            borderRadius: BorderRadius.circular(EvRadius.pill),
            child: Container(
              height: height,
              width: width,
              color: EvColors.surfaceHigh,
              child: Stack(
                children: [
                  for (final c in session.chunks)
                    Positioned(
                      left: (c.startMs / total).clamp(0.0, 1.0) * width,
                      width: width < 2
                          ? width
                          : ((c.durationMs / total).clamp(0.0, 1.0) * width)
                                .clamp(2.0, width),
                      top: 0,
                      bottom: 0,
                      child: const ColoredBox(color: EvColors.teal),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
