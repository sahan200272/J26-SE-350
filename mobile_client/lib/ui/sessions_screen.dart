import 'dart:async';

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import '../sync/syncthing_status.dart';
import 'components.dart';
import 'display_format.dart';
import 'pc_link_card.dart';
import 'session_detail_screen.dart';
import 'session_dialogs.dart';
import 'settings_screen.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Recordings stored on this phone, newest first, with search and a
/// day filter (All / Today / Older). Reloads when [refreshToken] changes and
/// on pull-to-refresh. Each row's menu offers the existing Rename and Delete.
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
  static const filterKey = Key('sessions-filter');

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
  _DayFilter _dayFilter = _DayFilter.all;

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
    // The navigation bar floats over this screen; keep the list clear of it.
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    // EmberScope: dialogs opened here (rename, delete) use the Ember look.
    return EmberScope(
      child: Scaffold(
      backgroundColor: EvEmber.black,
      body: Stack(
        fit: StackFit.expand,
        children: [
          const EmberBackdrop(),
          SafeArea(
            bottom: false,
            child: RefreshIndicator(
              color: EvEmber.accent,
              backgroundColor: EvEmber.deep,
              onRefresh: _load,
              child: ListView(
                key: SessionsScreen.listKey,
                physics: const AlwaysScrollableScrollPhysics(),
                padding: EdgeInsets.fromLTRB(
                  EvSpace.md,
                  EvSpace.xs,
                  EvSpace.md,
                  EvSpace.xl + bottomInset,
                ),
                children: [
                  _SessionsHeader(
                    subtitle: sessions == null
                        ? null
                        : sessions.isEmpty
                        ? 'Nothing recorded yet'
                        : '${plural(sessions.length, 'recording')} on this '
                              'phone',
                    onNewRecording: widget.onStartRecording,
                  ),
                  if (widget.syncthing != null && sessions != null) ...[
                    const SizedBox(height: EvSpace.sm),
                    _GlassPcLink(status: _sync, onTap: _openPairing),
                  ],
                  if (_failed && sessions == null)
                    _GlassMessage(
                      child: EmptyState(
                        key: SessionsScreen.errorKey,
                        icon: Icons.error_outline_rounded,
                        title: 'Recordings could not be loaded',
                        message: 'Something went wrong reading this phone’s '
                            'storage. Pull down or try again.',
                        action: OutlinedButton.icon(
                          onPressed: _load,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: const BorderSide(
                              color: EvEmber.glassBorder,
                            ),
                            shape: const StadiumBorder(),
                          ),
                          icon: const Icon(Icons.refresh_rounded),
                          label: const Text('Try again'),
                        ),
                      ),
                    )
                  else if (sessions == null)
                    const Column(
                      key: SessionsScreen.loadingKey,
                      children: [
                        SizedBox(height: EvSpace.md),
                        _CardSkeleton(),
                        SizedBox(height: EvSpace.sm),
                        _CardSkeleton(),
                        SizedBox(height: EvSpace.sm),
                        _CardSkeleton(),
                      ],
                    )
                  else if (sessions.isEmpty)
                    _GlassMessage(
                      child: EmptyState(
                        key: SessionsScreen.emptyKey,
                        icon: Icons.graphic_eq_rounded,
                        title: 'No recordings yet',
                        message:
                            'Conversations you record appear here, ready to '
                            'be sent to your PC.',
                        action: widget.onStartRecording == null
                            ? null
                            : FilledButton.icon(
                                onPressed: widget.onStartRecording,
                                style: FilledButton.styleFrom(
                                  backgroundColor: Colors.white,
                                  foregroundColor: EvEmber.black,
                                  shape: const StadiumBorder(),
                                ),
                                icon: const Icon(Icons.mic_rounded),
                                label: const Text('Start recording'),
                              ),
                      ),
                    )
                  else
                    ..._grouped(sessions),
                ],
              ),
            ),
          ),
        ],
      ),
      ),
    );
  }

  void _snack(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  String _errorText(Object e) => e is SessionActionException
      ? e.message
      : 'Something went wrong. Nothing was changed.';

  /// Row menu: the same rename as the detail screen (dialog + store).
  Future<void> _rename(SessionSummary s) async {
    final title = await showRenameDialog(context, current: sessionTitle(s));
    if (title == null || !mounted) return;
    try {
      await widget.source.rename(s.id, title);
      if (!mounted) return;
      _snack(SessionDetailScreen.renamedMessage);
    } catch (e) {
      if (mounted) _snack(_errorText(e));
    }
    if (mounted) await _load();
  }

  /// Row menu: the same delete as the detail screen (confirmation that says
  /// what happens to the PC copy, then the store's guarded delete).
  Future<void> _delete(SessionSummary s) async {
    final pcCopy = await _pcCopyState(s.id);
    if (!mounted) return;
    final confirmed = await showDeleteDialog(
      context,
      title: sessionTitle(s),
      pcCopy: pcCopy,
    );
    if (!confirmed || !mounted) return;
    try {
      await widget.source.delete(s.id);
      if (!mounted) return;
      _snack(SessionDetailScreen.deletedMessage);
    } catch (e) {
      if (mounted) _snack(_errorText(e));
    }
    if (mounted) await _load();
  }

  Future<PcCopyState> _pcCopyState(String id) async {
    final client = widget.syncthing;
    if (client == null) return PcCopyState.unknown;
    try {
      final pending = await client
          .sessionPendingFiles(id)
          .timeout(const Duration(seconds: 3));
      return switch (pending) {
        null => PcCopyState.unknown,
        0 => PcCopyState.sent,
        _ => PcCopyState.partlySent,
      };
    } catch (_) {
      return PcCopyState.unknown;
    }
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

  /// Sessions in the chosen day filter whose title or day matches the
  /// search text.
  List<SessionSummary> _filter(List<SessionSummary> sessions) {
    final q = _query.trim().toLowerCase();
    final now = widget.now();
    final today = DateTime(now.year, now.month, now.day);
    bool isToday(SessionSummary s) {
      final t = s.start;
      return t != null && DateTime(t.year, t.month, t.day) == today;
    }

    bool inDayFilter(SessionSummary s) => switch (_dayFilter) {
      _DayFilter.all => true,
      _DayFilter.today => isToday(s),
      _DayFilter.older => !isToday(s),
    };

    bool matchesQuery(SessionSummary s) =>
        q.isEmpty ||
        sessionTitle(s).toLowerCase().contains(q) ||
        (s.start != null && formatDay(s.start!, now).toLowerCase().contains(q));

    return [
      for (final s in sessions)
        if (inDayFilter(s) && matchesQuery(s)) s,
    ];
  }

  List<Widget> _grouped(List<SessionSummary> all) {
    final now = widget.now();
    final widgets = <Widget>[
      const SizedBox(height: EvSpace.md),
      _SearchField(
        controller: _search,
        onChanged: (value) => setState(() => _query = value),
      ),
      const SizedBox(height: EvSpace.sm),
      _DayFilterChips(
        key: SessionsScreen.filterKey,
        selected: _dayFilter,
        onSelected: (f) => setState(() => _dayFilter = f),
      ),
    ];
    final sessions = _filter(all);
    if (sessions.isEmpty) {
      widgets.add(
        const EmptyState(
          key: SessionsScreen.noMatchKey,
          icon: Icons.search_off_rounded,
          title: 'No matching recordings',
          message: 'Try a different name, day or filter.',
        ),
      );
      return widgets;
    }
    String? currentDay;
    for (final s in sessions) {
      final day = s.start == null ? 'Unknown date' : formatDay(s.start!, now);
      if (day != currentDay) {
        currentDay = day;
        widgets.add(_DayLabel(day));
      } else {
        widgets.add(const SizedBox(height: EvSpace.sm));
      }
      widgets.add(
        SessionTile(
          session: s,
          onTap: () => _open(s),
          onRename: () => _rename(s),
          onDelete: () => _delete(s),
        ),
      );
    }
    return widgets;
  }
}

enum _DayFilter { all, today, older }

/// All / Today / Older.
class _DayFilterChips extends StatelessWidget {
  const _DayFilterChips({
    super.key,
    required this.selected,
    required this.onSelected,
  });

  final _DayFilter selected;
  final ValueChanged<_DayFilter> onSelected;

  static String _label(_DayFilter f) => switch (f) {
    _DayFilter.all => 'All',
    _DayFilter.today => 'Today',
    _DayFilter.older => 'Older',
  };

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Wrap(
      spacing: EvSpace.xs,
      runSpacing: EvSpace.xs,
      children: [
        for (final f in _DayFilter.values)
          ChoiceChip(
            label: Text(_label(f)),
            selected: f == selected,
            onSelected: (_) => onSelected(f),
            showCheckmark: false,
            shape: const StadiumBorder(),
            side: BorderSide(
              color: f == selected
                  ? EvEmber.accent.withValues(alpha: 0.7)
                  : EvEmber.glassBorder,
            ),
            backgroundColor: EvEmber.glass,
            selectedColor: EvEmber.accent.withValues(alpha: 0.22),
            labelStyle: textTheme.labelLarge?.copyWith(
              color: f == selected ? Colors.white : EvEmber.textSoft,
            ),
          ),
      ],
    );
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
      // EmberScope above the screen: its rename / delete dialogs match it.
      builder: (_) => EmberScope(
        child: SessionDetailScreen(
          session: session,
          source: source,
          syncthing: syncthing,
        ),
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

/// One recording as a liquid-glass card: title, date and time, pauses,
/// length, speech activity, status, whether a transcript is available, and
/// (when given) a menu with Rename and Delete.
class SessionTile extends StatelessWidget {
  const SessionTile({
    super.key,
    required this.session,
    this.onTap,
    this.onRename,
    this.onDelete,
  });

  final SessionSummary session;
  final VoidCallback? onTap;

  /// Row menu actions; the menu is hidden when both are null.
  final VoidCallback? onRename;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final s = session;
    final length = s.recordedMs ?? s.sessionEndMs;
    final hasMenu = onRename != null || onDelete != null;
    return LiquidGlass(
      onTap: onTap,
      radius: 22,
      padding: EdgeInsets.fromLTRB(
        EvSpace.md,
        EvSpace.md,
        hasMenu ? EvSpace.xxs : EvSpace.md,
        EvSpace.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: EvEmber.glassStrong,
                  border: Border.all(color: EvEmber.glassBorder),
                ),
                child: const Icon(
                  Icons.graphic_eq_rounded,
                  color: Colors.white,
                  size: 20,
                ),
              ),
              const SizedBox(width: EvSpace.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sessionTitle(s),
                      style: textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: EvSpace.xxs),
                    Wrap(
                      spacing: EvSpace.sm,
                      runSpacing: 2,
                      children: [
                        _Meta(
                          icon: Icons.calendar_today_outlined,
                          text: s.start == null
                              ? 'Unknown date'
                              : formatDateTime(s.start!),
                        ),
                        if (s.pauseCount > 0)
                          _Meta(
                            icon: Icons.pause_circle_outline_rounded,
                            text: plural(s.pauseCount, 'pause'),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              if (hasMenu)
                _RowMenu(
                  title: sessionTitle(s),
                  onRename: onRename,
                  onDelete: onDelete,
                ),
            ],
          ),
          const SizedBox(height: EvSpace.sm),
          const Divider(color: EvEmber.hairline, height: 1),
          const SizedBox(height: EvSpace.sm),
          Padding(
            padding: EdgeInsets.only(right: hasMenu ? EvSpace.sm : 0),
            child: Row(
              children: [
                const Icon(
                  Icons.schedule_rounded,
                  size: 15,
                  color: EvEmber.textSoft,
                ),
                const SizedBox(width: 6),
                Text(
                  length == null ? '–' : formatSpan(length),
                  style: textTheme.labelLarge?.copyWith(
                    color: Colors.white,
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
                const SizedBox(width: EvSpace.sm),
                Expanded(
                  child: s.chunks.isNotEmpty && s.timelineMs > 0
                      ? SessionTimeline(
                          session: s,
                          height: 4,
                          color: EvEmber.accent,
                          trackColor: EvEmber.hairline,
                        )
                      : const SizedBox.shrink(),
                ),
                const SizedBox(width: EvSpace.sm),
                SessionStatusPill(session: s),
              ],
            ),
          ),
          const SizedBox(height: EvSpace.xs),
          const TranscriptAvailability(color: EvEmber.textFaint),
        ],
      ),
    );
  }
}

/// Small icon + text, e.g. the date line of a card.
class _Meta extends StatelessWidget {
  const _Meta({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: EvEmber.textFaint),
        const SizedBox(width: 4),
        Flexible(
          child: Text(
            text,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: EvEmber.textSoft),
          ),
        ),
      ],
    );
  }
}

enum _RowAction { rename, delete }

/// The "⋯" menu of a row.
class _RowMenu extends StatelessWidget {
  const _RowMenu({
    required this.title,
    required this.onRename,
    required this.onDelete,
  });

  final String title;
  final VoidCallback? onRename;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<_RowAction>(
      tooltip: 'More options for $title',
      icon: const Icon(Icons.more_vert_rounded, color: EvEmber.textSoft),
      color: const Color(0xFF241011),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.md),
      ),
      onSelected: (action) {
        switch (action) {
          case _RowAction.rename:
            onRename?.call();
          case _RowAction.delete:
            onDelete?.call();
        }
      },
      itemBuilder: (context) => [
        if (onRename != null)
          const PopupMenuItem(
            value: _RowAction.rename,
            child: ListTile(
              leading: Icon(Icons.edit_outlined),
              title: Text('Rename'),
              contentPadding: EdgeInsets.zero,
            ),
          ),
        if (onDelete != null)
          const PopupMenuItem(
            value: _RowAction.delete,
            child: ListTile(
              leading: Icon(
                Icons.delete_outline_rounded,
                color: EvColors.recording,
              ),
              title: Text(
                'Delete recording',
                style: TextStyle(color: EvColors.recording),
              ),
              contentPadding: EdgeInsets.zero,
            ),
          ),
      ],
    );
  }
}

/// One line saying whether a transcript can be shown. Transcripts are made
/// on the PC and are never sent back to the phone in this version.
class TranscriptAvailability extends StatelessWidget {
  const TranscriptAvailability({super.key, this.color = EvColors.textSubtle});

  static const label = 'Transcript not available on this phone yet';

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(Icons.notes_rounded, size: 16, color: color),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: color),
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
      style: const TextStyle(color: Colors.white),
      cursorColor: EvEmber.accent,
      textInputAction: TextInputAction.search,
      decoration: InputDecoration(
        hintText: 'Search recordings…',
        hintStyle: const TextStyle(color: EvEmber.textFaint),
        prefixIcon: const Icon(Icons.search_rounded, color: EvEmber.textSoft),
        suffixIcon: ListenableBuilder(
          listenable: controller,
          builder: (context, _) => controller.text.isEmpty
              ? const SizedBox.shrink()
              : IconButton(
                  tooltip: 'Clear search',
                  icon: const Icon(
                    Icons.close_rounded,
                    color: EvEmber.textSoft,
                  ),
                  onPressed: () {
                    controller.clear();
                    onChanged('');
                  },
                ),
        ),
        filled: true,
        fillColor: EvEmber.glass,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(vertical: EvSpace.sm),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(EvRadius.pill),
          borderSide: const BorderSide(color: EvEmber.glassBorder),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(EvRadius.pill),
          borderSide: const BorderSide(color: EvEmber.glassBorder),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(EvRadius.pill),
          borderSide: BorderSide(
            color: EvEmber.accent.withValues(alpha: 0.7),
          ),
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
  const SessionTimeline({
    super.key,
    required this.session,
    this.height = 8,
    this.color = EvColors.teal,
    this.trackColor = EvColors.surfaceHigh,
  });

  final SessionSummary session;
  final double height;

  /// Speech parts and the track behind them.
  final Color color;
  final Color trackColor;

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
              color: trackColor,
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
                      child: ColoredBox(color: color),
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

/// "Your Recordings", the count, and a glass "+" that starts a new
/// recording (the same action as the microphone on Home).
class _SessionsHeader extends StatelessWidget {
  const _SessionsHeader({required this.subtitle, this.onNewRecording});

  final String? subtitle;
  final VoidCallback? onNewRecording;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.xxs,
        EvSpace.md,
        0,
        EvSpace.xs,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  header: true,
                  child: Text(
                    'Your Recordings',
                    style: textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: EvSpace.xxs),
                  Text(
                    subtitle!,
                    style: textTheme.bodyMedium?.copyWith(
                      color: EvEmber.textSoft,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (onNewRecording != null)
            IconButton(
              tooltip: 'New recording',
              onPressed: onNewRecording,
              style: IconButton.styleFrom(
                backgroundColor: EvEmber.glassStrong,
                foregroundColor: Colors.white,
                side: const BorderSide(color: EvEmber.glassBorder),
                minimumSize: const Size(48, 48),
              ),
              icon: const Icon(Icons.add_rounded),
            ),
        ],
      ),
    );
  }
}

/// The PC connection line as a glass card (same text as [PcLinkCard]).
class _GlassPcLink extends StatelessWidget {
  const _GlassPcLink({required this.status, required this.onTap});

  final SyncthingStatus? status;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final info = PcLinkInfo.of(status);
    return LiquidGlass(
      key: PcLinkCard.cardKey,
      onTap: onTap,
      radius: 20,
      padding: const EdgeInsets.symmetric(
        horizontal: EvSpace.md,
        vertical: EvSpace.sm,
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: info.color.withValues(alpha: 0.16),
            ),
            child: Icon(info.icon, size: 18, color: info.color),
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  info.title,
                  style: textTheme.titleSmall?.copyWith(color: Colors.white),
                ),
                const SizedBox(height: 2),
                Text(
                  info.subtitle,
                  style: textTheme.bodySmall?.copyWith(
                    color: EvEmber.textSoft,
                  ),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: EvEmber.textFaint),
        ],
      ),
    );
  }
}

/// Uppercase day heading above a group of cards.
class _DayLabel extends StatelessWidget {
  const _DayLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.xxs,
        EvSpace.lg,
        EvSpace.xxs,
        EvSpace.sm,
      ),
      child: Text(
        text.toUpperCase(),
        style: Theme.of(
          context,
        ).textTheme.labelSmall?.copyWith(color: EvEmber.textFaint),
      ),
    );
  }
}

/// Empty and error states on a glass card, with light text.
class _GlassMessage extends StatelessWidget {
  const _GlassMessage({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: EvSpace.md),
      child: LiquidGlass(
        padding: EdgeInsets.zero,
        child: Theme(
          data: theme.copyWith(
            textTheme: theme.textTheme.apply(
              bodyColor: Colors.white,
              displayColor: Colors.white,
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}

/// Placeholder card while recordings load.
class _CardSkeleton extends StatelessWidget {
  const _CardSkeleton();

  @override
  Widget build(BuildContext context) {
    Widget bar(double width, double height) => Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: EvEmber.glassStrong,
        borderRadius: BorderRadius.circular(EvRadius.sm),
      ),
    );
    return ExcludeSemantics(
      child: LiquidGlass(
        radius: 22,
        child: Row(
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: EvEmber.glassStrong,
              ),
            ),
            const SizedBox(width: EvSpace.sm),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                bar(150, 12),
                const SizedBox(height: EvSpace.xs),
                bar(100, 10),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
