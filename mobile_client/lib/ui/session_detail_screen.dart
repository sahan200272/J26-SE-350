import 'dart:async';

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'display_format.dart';
import 'session_dialogs.dart';
import 'sessions_screen.dart';
import 'theme/app_theme.dart';

/// One recording: when and how long, its status, the transcript area (an
/// honest "not available yet" state, because transcripts are produced on
/// the PC and are not sent back to the phone), speech activity, and a
/// collapsed technical section for researchers.
///
/// The overflow menu renames or deletes the recording through [source].
/// Pops with `true` after a successful deletion.
class SessionDetailScreen extends StatefulWidget {
  const SessionDetailScreen({
    super.key,
    required this.session,
    this.source,
    this.syncthing,
  });

  final SessionSummary session;

  /// Rename and delete; the menu is hidden when null.
  final SessionSource? source;

  /// Used only to tell the user whether the PC already has the recording.
  final SyncthingClient? syncthing;

  static const transcriptKey = Key('session-transcript');
  static const technicalKey = Key('session-technical');
  static const chunkListKey = Key('session-chunks');
  static const menuKey = Key('session-menu');
  static const renameItemKey = Key('session-menu-rename');
  static const deleteItemKey = Key('session-menu-delete');
  static const titleKey = Key('session-title');
  static const busyKey = Key('session-busy');

  static const deletedMessage = 'Recording deleted from this phone';
  static const renamedMessage = 'Recording renamed';

  @override
  State<SessionDetailScreen> createState() => _SessionDetailScreenState();
}

enum _MenuAction { rename, delete }

class _SessionDetailScreenState extends State<SessionDetailScreen> {
  late SessionSummary _session = widget.session;
  bool _busy = false;

  void _snack(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  String _errorText(Object e) => e is SessionActionException
      ? e.message
      : 'Something went wrong. Nothing was changed.';

  Future<void> _rename() async {
    final source = widget.source;
    if (source == null) return;
    final title = await showRenameDialog(
      context,
      current: sessionTitle(_session),
    );
    if (title == null || !mounted) return;
    setState(() => _busy = true);
    try {
      await source.rename(_session.id, title);
      if (!mounted) return;
      setState(() => _session = _session.withTitle(title));
      _snack(SessionDetailScreen.renamedMessage);
    } catch (e) {
      if (mounted) _snack(_errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<PcCopyState> _pcCopyState() async {
    final client = widget.syncthing;
    if (client == null) return PcCopyState.unknown;
    try {
      final pending = await client
          .sessionPendingFiles(_session.id)
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

  Future<void> _delete() async {
    final source = widget.source;
    if (source == null) return;
    setState(() => _busy = true);
    final pcCopy = await _pcCopyState();
    if (!mounted) return;
    setState(() => _busy = false);
    final confirmed = await showDeleteDialog(
      context,
      title: sessionTitle(_session),
      pcCopy: pcCopy,
    );
    if (!confirmed || !mounted) return;
    setState(() => _busy = true);
    try {
      await source.delete(_session.id);
      if (!mounted) return;
      _snack(SessionDetailScreen.deletedMessage);
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _busy = false);
      _snack(_errorText(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_busy,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Recording'),
          centerTitle: false,
          bottom: _busy
              ? const PreferredSize(
                  preferredSize: Size.fromHeight(2),
                  child: LinearProgressIndicator(
                    key: SessionDetailScreen.busyKey,
                    minHeight: 2,
                  ),
                )
              : null,
          actions: [
            if (widget.source != null)
              PopupMenuButton<_MenuAction>(
                key: SessionDetailScreen.menuKey,
                tooltip: 'More options',
                enabled: !_busy,
                icon: const Icon(Icons.more_vert_rounded),
                color: EvColors.surfaceHigh,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(EvRadius.md),
                ),
                onSelected: (action) => unawaited(switch (action) {
                  _MenuAction.rename => _rename(),
                  _MenuAction.delete => _delete(),
                }),
                itemBuilder: (context) => const [
                  PopupMenuItem(
                    key: SessionDetailScreen.renameItemKey,
                    value: _MenuAction.rename,
                    child: ListTile(
                      leading: Icon(Icons.edit_outlined),
                      title: Text('Rename'),
                      contentPadding: EdgeInsets.zero,
                    ),
                  ),
                  PopupMenuItem(
                    key: SessionDetailScreen.deleteItemKey,
                    value: _MenuAction.delete,
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
              ),
            const SizedBox(width: EvSpace.xxs),
          ],
        ),
        body: SafeArea(
          child: AbsorbPointer(
            absorbing: _busy,
            child: _SessionDetailBody(session: _session),
          ),
        ),
      ),
    );
  }
}

class _SessionDetailBody extends StatelessWidget {
  const _SessionDetailBody({required this.session});

  final SessionSummary session;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final s = session;
    final length = s.recordedMs ?? s.sessionEndMs;
    return ListView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.xs,
            EvSpace.md,
            EvSpace.xl,
          ),
          children: [
            // Header.
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: EvSpace.xxs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    s.start == null ? 'Unknown date' : formatDateTime(s.start!),
                    style: textTheme.bodyMedium?.copyWith(
                      color: EvColors.textMuted,
                    ),
                  ),
                  const SizedBox(height: EvSpace.xxs),
                  Text(
                    key: SessionDetailScreen.titleKey,
                    sessionTitle(s),
                    style: textTheme.headlineSmall,
                  ),
                  const SizedBox(height: EvSpace.sm),
                  Wrap(
                    spacing: EvSpace.xs,
                    runSpacing: EvSpace.xs,
                    children: [
                      SessionStatusPill(session: s),
                      if (length != null)
                        StatusPill(
                          label: formatSpan(length),
                          icon: Icons.timer_outlined,
                        ),
                      if (s.pauseCount > 0)
                        StatusPill(
                          label: plural(s.pauseCount, 'pause'),
                          icon: Icons.pause_rounded,
                        ),
                    ],
                  ),
                ],
              ),
            ),
            if (s.error != null) ...[
              const SizedBox(height: EvSpace.md),
              const NoticeCard(
                icon: Icons.error_outline_rounded,
                title: 'This recording can’t be opened',
                message:
                    'Its files on this phone could not be read. Details are '
                    'under Technical details.',
                tone: PillTone.danger,
              ),
            ] else if (!s.complete) ...[
              const SizedBox(height: EvSpace.md),
              const NoticeCard(
                icon: Icons.hourglass_bottom_rounded,
                title: 'Recording incomplete',
                message:
                    'It may still be saving, or the app closed before the '
                    'recording was stopped. The parts already saved are kept.',
                tone: PillTone.warning,
              ),
            ],

            // Transcript.
            const SectionTitle('Transcript'),
            const EvCard(
              key: SessionDetailScreen.transcriptKey,
              padding: EdgeInsets.all(EvSpace.lg),
              child: _TranscriptUnavailable(),
            ),

            // Speech activity.
            if (s.chunks.isNotEmpty && s.timelineMs > 0) ...[
              const SectionTitle('Speech activity'),
              EvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    SessionTimeline(session: s, height: 14),
                    const SizedBox(height: EvSpace.xs),
                    Row(
                      children: [
                        Text(formatOffset(0), style: textTheme.bodySmall),
                        const Spacer(),
                        Text(
                          formatOffset(s.timelineMs),
                          style: textTheme.bodySmall,
                        ),
                      ],
                    ),
                    const SizedBox(height: EvSpace.sm),
                    Text(
                      'Speech was heard in ${plural(s.chunkCount, 'part')} '
                      'of this recording (${formatSpan(s.speechMs)} in '
                      'total). Silence is not kept.',
                      style: textTheme.bodyMedium?.copyWith(
                        color: EvColors.textMuted,
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // Technical details (collapsed).
            const SizedBox(height: EvSpace.lg),
            _TechnicalDetails(session: s),
          ],
    );
  }
}

class _TranscriptUnavailable extends StatelessWidget {
  const _TranscriptUnavailable();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Column(
      children: [
        const IconBadge(Icons.notes_rounded, color: EvColors.indigo, size: 52),
        const SizedBox(height: EvSpace.md),
        Text(
          'Transcript not available on this phone yet',
          style: textTheme.titleMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: EvSpace.xs),
        Text(
          'Transcripts are created by Echo Vault on your PC. Showing them '
          'here, with speaker names, times and highlights, is planned but '
          'not built yet.',
          style: textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

/// Collapsed by default: identifiers and file-level details for research
/// and troubleshooting.
class _TechnicalDetails extends StatelessWidget {
  const _TechnicalDetails({required this.session});

  final SessionSummary session;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final s = session;
    final mono = textTheme.bodySmall?.copyWith(
      fontFamily: 'monospace',
      color: EvColors.textMuted,
    );
    Widget row(String label, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 128,
            child: Text(label, style: textTheme.bodySmall),
          ),
          Expanded(child: SelectableText(value, style: mono)),
        ],
      ),
    );
    return EvCard(
      key: SessionDetailScreen.technicalKey,
      padding: EdgeInsets.zero,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: EvSpace.md),
          childrenPadding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            0,
            EvSpace.md,
            EvSpace.md,
          ),
          leading: const Icon(Icons.code_rounded, color: EvColors.textMuted),
          title: Text('Technical details', style: textTheme.titleSmall),
          subtitle: Text(
            'For research and troubleshooting',
            style: textTheme.bodySmall,
          ),
          expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            row('Session ID', s.id),
            row('Manifest', s.complete ? 'written' : 'missing'),
            row('VAD', s.vadType ?? '–'),
            row('Speech chunks', '${s.chunkCount}'),
            if (s.failedChunks > 0) row('Failed chunks', '${s.failedChunks}'),
            row(
              'Opus size',
              s.opusBytes == 0 ? '–' : formatBytes(s.opusBytes),
            ),
            if (s.encoderBitrate case final bitrate?)
              row('Opus bitrate', '${bitrate ~/ 1000} kbit/s'),
            if (s.error case final error?) row('Read error', error),
            if (s.chunks.isNotEmpty) ...[
              const SizedBox(height: EvSpace.sm),
              Text(
                'Chunks (start – end, length, size)',
                style: textTheme.bodySmall,
              ),
              const SizedBox(height: EvSpace.xs),
              Column(
                key: SessionDetailScreen.chunkListKey,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  for (final c in s.chunks)
                    Text(
                      '#${c.seq.toString().padLeft(2, '0')}  '
                      '${formatOffset(c.startMs)} – ${formatOffset(c.endMs)}  '
                      '${formatSpan(c.durationMs)}'
                      '${c.opusBytes == null ? '' : '  ${formatBytes(c.opusBytes!)}'}',
                      style: mono,
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
