import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sessions/session_titles.dart';
import 'elapsed_format.dart';
import 'live_waveform.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Shows the "Name This Recording" sheet after Stop.
///
/// The recording is already being saved by the existing pipeline when this
/// opens (Stop writes the manifest); the sheet only lets the user give it a
/// name through the existing rename ([onRename]). Cancel, the close button
/// or swiping the sheet away keeps the recording with its automatic name;
/// nothing is deleted.
///
/// Returns the name the recording now has, or null if the sheet was closed
/// without saving a name.
Future<String?> showSaveRecordingSheet(
  BuildContext context, {
  required String defaultTitle,
  required Duration duration,
  required List<double> levels,
  required Future<Map<String, Object?>> saved,
  required Future<void> Function(String title) onRename,
}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    backgroundColor: const Color(0xFF170707),
    barrierColor: Colors.black.withValues(alpha: 0.6),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    ),
    clipBehavior: Clip.antiAlias,
    // The Ember look (white Save, glass field) for the sheet's content.
    builder: (_) => EmberScope(
      child: SaveRecordingSheet(
      defaultTitle: defaultTitle,
      duration: duration,
      levels: levels,
      saved: saved,
      onRename: onRename,
      ),
    ),
  );
}

/// The sheet's content (public so it can be tested on its own).
class SaveRecordingSheet extends StatefulWidget {
  const SaveRecordingSheet({
    super.key,
    required this.defaultTitle,
    required this.duration,
    required this.levels,
    required this.saved,
    required this.onRename,
  });

  /// The automatic name, e.g. `Recording at 14:05`; pre-filled.
  final String defaultTitle;

  /// Recorded time, excluding pauses.
  final Duration duration;

  /// The last real microphone levels of the recording (0..1).
  final List<double> levels;

  /// Completes with the session manifest once the recording is stored.
  final Future<Map<String, Object?>> saved;

  /// Saves a new title (the existing [SessionSource.rename]).
  final Future<void> Function(String title) onRename;

  static const sheetKey = Key('save-sheet');
  static const fieldKey = Key('save-sheet-name');
  static const saveKey = Key('save-sheet-save');
  static const cancelKey = Key('save-sheet-cancel');
  static const closeKey = Key('save-sheet-close');
  static const statusKey = Key('save-sheet-status');

  static const title = 'Name This Recording';
  static const emptyNameMessage = 'Enter a name for the recording.';
  static const renameFailedMessage =
      'The name could not be saved. The recording itself is kept on this '
      'phone.';

  @override
  State<SaveRecordingSheet> createState() => _SaveRecordingSheetState();
}

class _SaveRecordingSheetState extends State<SaveRecordingSheet> {
  late final _text = TextEditingController(text: widget.defaultTitle)
    ..selection = TextSelection(
      baseOffset: 0,
      extentOffset: widget.defaultTitle.length,
    );
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _close() => Navigator.of(context).pop();

  Future<void> _save() async {
    final title = normalizeSessionTitle(_text.text);
    if (title == null) {
      setState(() => _error = SaveRecordingSheet.emptyNameMessage);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    // Wait for the existing save to finish, so the recording's folder is
    // complete before it is named. A partly failed save is still named.
    try {
      await widget.saved;
    } catch (_) {}
    if (!mounted) return;
    // An unchanged automatic name needs no rename.
    if (title != widget.defaultTitle) {
      try {
        await widget.onRename(title);
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _busy = false;
          _error = e is SessionActionException
              ? e.message
              : SaveRecordingSheet.renameFailedMessage;
        });
        return;
      }
    }
    if (mounted) Navigator.of(context).pop(title);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final keyboard = MediaQuery.viewInsetsOf(context).bottom;
    return PopScope(
      canPop: !_busy,
      child: Padding(
        key: SaveRecordingSheet.sheetKey,
        padding: EdgeInsets.only(bottom: keyboard),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.lg,
            EvSpace.sm,
            EvSpace.lg,
            EvSpace.lg,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: EvEmber.glassBorder,
                    borderRadius: BorderRadius.circular(EvRadius.pill),
                  ),
                ),
              ),
              const SizedBox(height: EvSpace.md),
              Row(
                children: [
                  Expanded(
                    child: Semantics(
                      header: true,
                      child: Text(
                        SaveRecordingSheet.title,
                        style: textTheme.titleLarge,
                      ),
                    ),
                  ),
                  const SizedBox(width: EvSpace.xs),
                  IconButton(
                    key: SaveRecordingSheet.closeKey,
                    tooltip: 'Close',
                    onPressed: _busy ? null : _close,
                    style: IconButton.styleFrom(
                      backgroundColor: EvEmber.glassStrong,
                      foregroundColor: Colors.white,
                    ),
                    icon: const Icon(Icons.close_rounded, size: 20),
                  ),
                ],
              ),
              const SizedBox(height: EvSpace.xxs),
              _SaveStatus(saved: widget.saved),
              const SizedBox(height: EvSpace.md),
              _AudioSummary(levels: widget.levels, duration: widget.duration),
              const SizedBox(height: EvSpace.md),
              TextField(
                key: SaveRecordingSheet.fieldKey,
                controller: _text,
                enabled: !_busy,
                maxLength: kMaxSessionTitleLength,
                textCapitalization: TextCapitalization.sentences,
                textInputAction: TextInputAction.done,
                onChanged: (_) {
                  if (_error != null) setState(() => _error = null);
                },
                onSubmitted: (_) => _save(),
                decoration: InputDecoration(
                  labelText: 'Recording name',
                  hintText: 'e.g. Weekly project meeting',
                  errorText: _error,
                  errorMaxLines: 3,
                  counterText: '',
                  filled: true,
                  fillColor: EvEmber.glass,
                  prefixIcon: const Icon(Icons.edit_outlined, size: 20),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvRadius.md),
                    borderSide: const BorderSide(color: EvEmber.glassBorder),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(EvRadius.md),
                    borderSide: const BorderSide(color: EvEmber.glassBorder),
                  ),
                ),
              ),
              const SizedBox(height: EvSpace.lg),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      key: SaveRecordingSheet.cancelKey,
                      onPressed: _busy ? null : _close,
                      style: OutlinedButton.styleFrom(
                        shape: const StadiumBorder(),
                      ),
                      child: const Text('Cancel'),
                    ),
                  ),
                  const SizedBox(width: EvSpace.sm),
                  Expanded(
                    child: FilledButton(
                      key: SaveRecordingSheet.saveKey,
                      onPressed: _busy ? null : _save,
                      style: FilledButton.styleFrom(
                        shape: const StadiumBorder(),
                      ),
                      child: _busy
                          ? const SizedBox.square(
                              dimension: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: EvEmber.textFaint,
                              ),
                            )
                          : const Text('Save'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// One line: whether the recording is already stored on the phone.
class _SaveStatus extends StatelessWidget {
  const _SaveStatus({required this.saved});

  final Future<Map<String, Object?>> saved;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.bodyMedium;
    return FutureBuilder<Map<String, Object?>>(
      future: saved,
      builder: (context, snapshot) {
        IconData icon = Icons.hourglass_top_rounded;
        Color color = EvEmber.textSoft;
        String text = 'Saving to this phone…';
        final data = snapshot.data;
        if (snapshot.hasError) {
          icon = Icons.warning_amber_rounded;
          color = EvColors.warning;
          text =
              'Some audio could not be saved. The rest is kept on this phone.';
        } else if (data != null) {
          final failed = (data['failed_chunks'] as List<Object?>?)?.length ?? 0;
          if (failed > 0) {
            icon = Icons.warning_amber_rounded;
            color = EvColors.warning;
            text = 'Saved on this phone, with a few gaps.';
          } else {
            icon = Icons.check_circle_outline_rounded;
            color = EvColors.success;
            text = 'Saved on this phone. Give it a name, or keep this one.';
          }
        }
        return Semantics(
          liveRegion: true,
          child: Row(
            key: SaveRecordingSheet.statusKey,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Icon(icon, size: 16, color: color),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  text,
                  style: style?.copyWith(color: EvEmber.textSoft),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// The recording at a glance: waveform of its real levels and its length.
/// (The app has no playback, so there is no play button.)
class _AudioSummary extends StatelessWidget {
  const _AudioSummary({required this.levels, required this.duration});

  final List<double> levels;
  final Duration duration;

  @override
  Widget build(BuildContext context) {
    final length = formatElapsed(duration);
    return Semantics(
      label: 'Recording length $length',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: EvSpace.sm,
          vertical: EvSpace.sm,
        ),
        decoration: BoxDecoration(
          color: EvEmber.glass,
          borderRadius: BorderRadius.circular(EvRadius.md),
          border: Border.all(color: EvEmber.glassBorder),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: EvEmber.accent.withValues(alpha: 0.18),
              ),
              child: const Icon(
                Icons.graphic_eq_rounded,
                size: 18,
                color: EvEmber.accentSoft,
              ),
            ),
            const SizedBox(width: EvSpace.sm),
            Expanded(
              child: LiveWaveform(
                levels: levels,
                active: levels.isNotEmpty,
                height: 32,
                bars: 32,
                animate: false,
              ),
            ),
            const SizedBox(width: EvSpace.sm),
            Container(
              width: 6,
              height: 6,
              decoration: const BoxDecoration(
                color: EvColors.recording,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 6),
            Text(
              length,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
