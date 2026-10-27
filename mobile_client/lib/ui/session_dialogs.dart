import 'package:flutter/material.dart';

import '../sessions/session_titles.dart';
import 'components.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Asks for a new recording title. Returns the cleaned-up title, or null if
/// the user cancelled or left the title unchanged.
Future<String?> showRenameDialog(
  BuildContext context, {
  required String current,
}) {
  return showDialog<String>(
    context: context,
    builder: (_) => _RenameDialog(current: current),
  );
}

class _RenameDialog extends StatefulWidget {
  const _RenameDialog({required this.current});

  final String current;

  @override
  State<_RenameDialog> createState() => _RenameDialogState();
}

class _RenameDialogState extends State<_RenameDialog> {
  late final _text = TextEditingController(text: widget.current)
    ..selection = TextSelection(
      baseOffset: 0,
      extentOffset: widget.current.length,
    );
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _save() {
    final title = normalizeSessionTitle(_text.text);
    if (title == null) {
      setState(() => _error = 'Enter a name for the recording.');
      return;
    }
    Navigator.of(context).pop(title == widget.current ? null : title);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: SessionDialogKeys.rename,
      backgroundColor: EvPalette.of(context).dialog,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.lg),
      ),
      title: const Text('Rename recording'),
      content: TextField(
        key: SessionDialogKeys.renameField,
        controller: _text,
        autofocus: true,
        maxLength: kMaxSessionTitleLength,
        textCapitalization: TextCapitalization.sentences,
        textInputAction: TextInputAction.done,
        onChanged: (_) {
          if (_error != null) setState(() => _error = null);
        },
        onSubmitted: (_) => _save(),
        decoration: InputDecoration(
          hintText: 'e.g. Weekly project meeting',
          errorText: _error,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(EvRadius.md),
          ),
        ),
      ),
      actions: [
        TextButton(
          key: SessionDialogKeys.cancel,
          onPressed: () => Navigator.of(context).pop(),
          style: TextButton.styleFrom(foregroundColor: EvColors.textMuted),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: SessionDialogKeys.save,
          onPressed: _save,
          child: const Text('Save'),
        ),
      ],
    );
  }
}

/// What is known about the PC copy when deleting.
enum PcCopyState {
  /// The PC has every file of the recording.
  sent,

  /// Some files have not reached the PC yet.
  partlySent,

  /// Not known (no PC set, PC link not running, or the check failed).
  unknown,
}

/// Confirms deleting [title]. Returns true only when the user taps Delete.
Future<bool> showDeleteDialog(
  BuildContext context, {
  required String title,
  required PcCopyState pcCopy,
}) async {
  final textTheme = Theme.of(context).textTheme;
  final pcLine = switch (pcCopy) {
    PcCopyState.sent =>
      'It has already been sent to your PC. The copy on your PC is kept.',
    PcCopyState.partlySent =>
      'Part of it has not reached your PC yet. Those parts will not be sent; '
          'anything already on your PC is kept.',
    PcCopyState.unknown =>
      'If it was already sent to your PC, the copy on your PC is kept.',
  };
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      key: SessionDialogKeys.delete,
      backgroundColor: EvPalette.of(context).dialog,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.lg),
      ),
      icon: const Icon(
        Icons.delete_outline_rounded,
        color: EvColors.recording,
        size: 32,
      ),
      title: const Text('Delete this recording?'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '“$title” and its audio will be removed from this phone. '
              'This can’t be undone.',
              style: textTheme.bodyMedium,
            ),
            const SizedBox(height: EvSpace.md),
            NoticeCard(
              icon: Icons.computer_rounded,
              message:
                  '$pcLine Transcripts already made on your PC are not '
                  'affected.',
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          key: SessionDialogKeys.cancel,
          onPressed: () => Navigator.of(context).pop(false),
          style: TextButton.styleFrom(foregroundColor: EvColors.snow),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: SessionDialogKeys.confirmDelete,
          onPressed: () => Navigator.of(context).pop(true),
          style: FilledButton.styleFrom(
            backgroundColor: EvColors.recordingDeep,
            foregroundColor: EvColors.snow,
          ),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
  return confirmed ?? false;
}

abstract final class SessionDialogKeys {
  static const rename = Key('rename-dialog');
  static const renameField = Key('rename-field');
  static const save = Key('rename-save');
  static const cancel = Key('dialog-cancel');
  static const delete = Key('delete-dialog');
  static const confirmDelete = Key('delete-confirm');
}
