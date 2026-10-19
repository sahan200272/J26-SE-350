import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'display_format.dart';
import 'session_dialogs.dart';
import 'sessions_screen.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// One recording, in the dark Ember look: when and how long, its status, a
/// speech-activity strip drawn from the real speech parts, key figures, the
/// transcript area (an honest "not available yet" state, because
/// transcripts are produced on the PC and are not sent back to the phone),
/// and a collapsed technical section for researchers.
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
        backgroundColor: EvEmber.black,
        extendBodyBehindAppBar: true,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          scrolledUnderElevation: 0,
          leading: Center(
            child: IconButton(
              tooltip: 'Back',
              onPressed: _busy ? null : () => Navigator.of(context).maybePop(),
              style: _glassIconStyle,
              icon: const Icon(Icons.arrow_back_rounded, size: 20),
            ),
          ),
          title: Text(
            'Recording',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: EvEmber.textSoft,
            ),
          ),
          centerTitle: true,
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
                style: _glassIconStyle,
                icon: const Icon(Icons.more_horiz_rounded, size: 20),
                color: const Color(0xFF241011),
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
            const SizedBox(width: EvSpace.xs),
          ],
        ),
        body: Stack(
          fit: StackFit.expand,
          children: [
            const _DetailBackdrop(),
            SafeArea(
              bottom: false,
              child: AbsorbPointer(
                absorbing: _busy,
                child: _SessionDetailBody(session: _session),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Small round frosted-glass icon buttons in the app bar.
final ButtonStyle _glassIconStyle = IconButton.styleFrom(
  backgroundColor: EvEmber.glass,
  foregroundColor: Colors.white,
  disabledForegroundColor: EvEmber.textFaint,
  side: const BorderSide(color: EvEmber.glassBorder),
);

/// Quiet background: near-black with one soft, low-saturation glow behind
/// the header (no strong red).
class _DetailBackdrop extends StatelessWidget {
  const _DetailBackdrop();

  @override
  Widget build(BuildContext context) {
    return const ExcludeSemantics(
      child: RepaintBoundary(
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment(0, -1.05),
              radius: 1.25,
              colors: [Color(0xFF2A0D0C), Color(0xFF110707), EvEmber.black],
              stops: [0, 0.5, 1],
            ),
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
    final hasSpeech = s.chunks.isNotEmpty && s.timelineMs > 0;
    return ListView(
      padding: EdgeInsets.fromLTRB(
        EvSpace.md,
        EvSpace.sm,
        EvSpace.md,
        EvSpace.xl + MediaQuery.paddingOf(context).bottom,
      ),
      children: [
        // Header.
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: EvSpace.xxs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(
                    Icons.calendar_today_outlined,
                    size: 14,
                    color: EvEmber.textFaint,
                  ),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      s.start == null
                          ? 'Unknown date'
                          : formatDateTime(s.start!),
                      style: textTheme.bodyMedium?.copyWith(
                        color: EvEmber.textSoft,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: EvSpace.xs),
              Text(
                key: SessionDetailScreen.titleKey,
                sessionTitle(s),
                style: textTheme.headlineMedium?.copyWith(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  height: 1.15,
                ),
              ),
              const SizedBox(height: EvSpace.sm),
              Wrap(
                spacing: EvSpace.xs,
                runSpacing: EvSpace.xs,
                children: [
                  SessionStatusPill(session: s),
                  if (length != null)
                    _Chip(icon: Icons.schedule_rounded, label: formatSpan(length)),
                  if (s.pauseCount > 0)
                    _Chip(
                      icon: Icons.pause_rounded,
                      label: plural(s.pauseCount, 'pause'),
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

        // Speech activity: the recording's timeline, with the parts where
        // speech was heard raised.
        const SizedBox(height: EvSpace.lg),
        LiquidGlass(
          radius: 24,
          shadow: false,
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.md,
            EvSpace.md,
            EvSpace.sm,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Text(
                    'Speech activity',
                    style: textTheme.titleSmall?.copyWith(color: Colors.white),
                  ),
                  const Spacer(),
                  if (hasSpeech)
                    Text(
                      plural(s.chunkCount, 'part'),
                      style: textTheme.bodySmall?.copyWith(
                        color: EvEmber.textFaint,
                      ),
                    ),
                ],
              ),
              const SizedBox(height: EvSpace.md),
              _SpeechBars(session: s, height: 56),
              const SizedBox(height: EvSpace.xs),
              Row(
                children: [
                  Text(
                    formatOffset(0),
                    style: _mono(textTheme, EvEmber.textFaint),
                  ),
                  const Spacer(),
                  Text(
                    formatOffset(s.timelineMs),
                    style: _mono(textTheme, EvEmber.textFaint),
                  ),
                ],
              ),
              const SizedBox(height: EvSpace.sm),
              Text(
                hasSpeech
                    ? 'Speech was heard in ${plural(s.chunkCount, 'part')} of '
                          'this recording (${formatSpan(s.speechMs)} in '
                          'total). Silence is not kept.'
                    : 'No speech was detected in this recording.',
                style: textTheme.bodySmall?.copyWith(color: EvEmber.textSoft),
              ),
            ],
          ),
        ),

        // Key figures.
        const SizedBox(height: EvSpace.sm),
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: _Stat(
                  label: 'Recorded',
                  value: length == null ? '–' : formatSpan(length),
                ),
              ),
              const SizedBox(width: EvSpace.sm),
              Expanded(
                child: _Stat(
                  label: 'Speech',
                  value: hasSpeech ? formatSpan(s.speechMs) : '–',
                ),
              ),
              const SizedBox(width: EvSpace.sm),
              Expanded(
                child: _Stat(
                  label: 'Parts',
                  value: '${s.chunkCount}',
                ),
              ),
            ],
          ),
        ),

        // Transcript.
        const SizedBox(height: EvSpace.lg),
        const _SectionHeading('Transcript'),
        const LiquidGlass(
          key: SessionDetailScreen.transcriptKey,
          radius: 20,
          shadow: false,
          child: _TranscriptUnavailable(),
        ),

        // Technical details (collapsed).
        const SizedBox(height: EvSpace.lg),
        _TechnicalDetails(session: s),
      ],
    );
  }
}

TextStyle? _mono(TextTheme textTheme, Color color) => textTheme.bodySmall
    ?.copyWith(
      color: color,
      fontFeatures: const [FontFeature.tabularFigures()],
    );

/// Small heading above a section.
class _SectionHeading extends StatelessWidget {
  const _SectionHeading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.xxs,
        0,
        EvSpace.xxs,
        EvSpace.sm,
      ),
      child: Text(
        text,
        style: Theme.of(
          context,
        ).textTheme.titleSmall?.copyWith(color: Colors.white),
      ),
    );
  }
}

/// Compact glass chip: icon + short label.
class _Chip extends StatelessWidget {
  const _Chip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: EvEmber.glass,
        borderRadius: BorderRadius.circular(EvRadius.pill),
        border: Border.all(color: EvEmber.glassBorder),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: EvEmber.textSoft),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

/// One key figure: a small label over a value.
class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return LiquidGlass(
      radius: 18,
      shadow: false,
      padding: const EdgeInsets.symmetric(
        horizontal: EvSpace.sm,
        vertical: EvSpace.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
          ),
          const SizedBox(height: 2),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              maxLines: 1,
              style: textTheme.titleMedium?.copyWith(
                color: Colors.white,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The recording as a row of bars across its timeline: bars where speech
/// was heard are tall and bright, the rest stay low. Drawn only from the
/// saved speech parts (no audio levels are stored, so this is not a fake
/// waveform).
class _SpeechBars extends StatelessWidget {
  const _SpeechBars({required this.session, required this.height});

  final SessionSummary session;
  final double height;

  @override
  Widget build(BuildContext context) {
    final total = session.timelineMs;
    return Semantics(
      label: 'Speech activity across ${formatSpan(total)}',
      excludeSemantics: true,
      child: SizedBox(
        height: height,
        width: double.infinity,
        child: CustomPaint(painter: _SpeechBarsPainter(session)),
      ),
    );
  }
}

class _SpeechBarsPainter extends CustomPainter {
  _SpeechBarsPainter(this.session);

  final SessionSummary session;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0) return;
    const slot = 6.0;
    final count = math.max(1, (size.width / slot).floor());
    const barWidth = 3.0;
    final total = session.timelineMs;
    final mid = size.height / 2;
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = barWidth;
    for (var i = 0; i < count; i++) {
      final x = slot * i + slot / 2;
      final t0 = total <= 0 ? 0.0 : total * i / count;
      final t1 = total <= 0 ? 0.0 : total * (i + 1) / count;
      final speech = session.chunks.any((c) => c.startMs < t1 && c.endMs > t0);
      // Speech bars vary gently in height so the strip reads as audio;
      // the variation is fixed per position, not invented level data.
      final shape = 0.55 + 0.45 * math.sin(i * 1.7).abs();
      final half = speech
          ? math.max(4.0, (size.height / 2 - 2) * shape)
          : 1.5;
      paint.color = speech
          ? Color.lerp(Colors.white, EvEmber.accentSoft, (i / count) * 0.8)!
          : Colors.white.withValues(alpha: 0.18);
      canvas.drawLine(Offset(x, mid - half), Offset(x, mid + half), paint);
    }
  }

  @override
  bool shouldRepaint(_SpeechBarsPainter old) => old.session != session;
}

class _TranscriptUnavailable extends StatelessWidget {
  const _TranscriptUnavailable();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: EvEmber.glassStrong,
            border: Border.all(color: EvEmber.glassBorder),
          ),
          child: const Icon(
            Icons.notes_rounded,
            size: 20,
            color: Colors.white,
          ),
        ),
        const SizedBox(width: EvSpace.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Transcript not available on this phone yet',
                style: textTheme.titleSmall?.copyWith(color: Colors.white),
              ),
              const SizedBox(height: EvSpace.xxs),
              Text(
                'Transcripts are created by Echo Vault on your PC. Showing '
                'them here, with speaker names, times and highlights, is '
                'planned but not built yet.',
                style: textTheme.bodySmall?.copyWith(color: EvEmber.textSoft),
              ),
            ],
          ),
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
      color: EvEmber.textSoft,
    );
    Widget row(String label, String value) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 128,
            child: Text(
              label,
              style: textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
            ),
          ),
          Expanded(child: SelectableText(value, style: mono)),
        ],
      ),
    );
    return LiquidGlass(
      key: SessionDetailScreen.technicalKey,
      radius: 20,
      shadow: false,
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
          iconColor: Colors.white,
          collapsedIconColor: EvEmber.textSoft,
          leading: const Icon(Icons.code_rounded, color: EvEmber.textSoft),
          title: Text(
            'Technical details',
            style: textTheme.titleSmall?.copyWith(color: Colors.white),
          ),
          subtitle: Text(
            'For research and troubleshooting',
            style: textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
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
                style: textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
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
