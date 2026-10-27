import 'dart:async';

import 'package:echo_vault/sessions/session_store.dart';
import 'package:echo_vault/ui/save_recording_sheet.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late List<String> renamed;
  late Object? renameError;
  late Completer<Map<String, Object?>> saved;
  String? result;
  late bool closed;

  setUp(() {
    renamed = [];
    renameError = null;
    saved = Completer<Map<String, Object?>>();
    result = null;
    closed = false;
  });

  /// A screen with a button that opens the sheet, like the recording screen
  /// does after Stop.
  Future<void> openSheet(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () async {
                  result = await showSaveRecordingSheet(
                    context,
                    defaultTitle: 'Recording at 14:05',
                    duration: const Duration(seconds: 12),
                    levels: const [0.2, 0.6, 0.4],
                    saved: saved.future,
                    onRename: (title) async {
                      if (renameError case final e?) throw e;
                      renamed.add(title);
                    },
                  );
                  closed = true;
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text(SaveRecordingSheet.title), findsOneWidget);
  }

  testWidgets('shows the default name, length and save progress', (
    tester,
  ) async {
    await openSheet(tester);
    expect(find.text('Recording at 14:05'), findsOneWidget);
    expect(find.text('00:12'), findsOneWidget);
    expect(find.text('Saving to this phone…'), findsOneWidget);

    saved.complete({'failed_chunks': <Object?>[]});
    await tester.pumpAndSettle();
    expect(find.textContaining('Saved on this phone'), findsOneWidget);
  });

  testWidgets('Save: waits for the save, renames with the trimmed name and '
      'closes', (tester) async {
    await openSheet(tester);
    await tester.enterText(
      find.byKey(SaveRecordingSheet.fieldKey),
      '  Weekly   sync ',
    );
    await tester.tap(find.byKey(SaveRecordingSheet.saveKey));
    await tester.pump();
    expect(renamed, isEmpty, reason: 'still saving');

    saved.complete({'failed_chunks': <Object?>[]});
    await tester.pumpAndSettle();
    expect(renamed, ['Weekly sync']);
    expect(closed, isTrue);
    expect(result, 'Weekly sync');
    expect(find.text(SaveRecordingSheet.title), findsNothing);
  });

  testWidgets('Save with the unchanged automatic name does not rename', (
    tester,
  ) async {
    saved.complete({'failed_chunks': <Object?>[]});
    await openSheet(tester);
    await tester.tap(find.byKey(SaveRecordingSheet.saveKey));
    await tester.pumpAndSettle();
    expect(renamed, isEmpty);
    expect(result, 'Recording at 14:05');
  });

  testWidgets('empty name is rejected; nothing is renamed', (tester) async {
    saved.complete({'failed_chunks': <Object?>[]});
    await openSheet(tester);
    await tester.enterText(find.byKey(SaveRecordingSheet.fieldKey), '   ');
    await tester.tap(find.byKey(SaveRecordingSheet.saveKey));
    await tester.pumpAndSettle();
    expect(find.text(SaveRecordingSheet.emptyNameMessage), findsOneWidget);
    expect(renamed, isEmpty);
    expect(closed, isFalse);
  });

  testWidgets('Cancel closes without renaming', (tester) async {
    saved.complete({'failed_chunks': <Object?>[]});
    await openSheet(tester);
    await tester.enterText(find.byKey(SaveRecordingSheet.fieldKey), 'Draft');
    await tester.tap(find.byKey(SaveRecordingSheet.cancelKey));
    await tester.pumpAndSettle();
    expect(renamed, isEmpty);
    expect(closed, isTrue);
    expect(result, isNull);
  });

  testWidgets('the close button closes without renaming', (tester) async {
    saved.complete({'failed_chunks': <Object?>[]});
    await openSheet(tester);
    await tester.tap(find.byKey(SaveRecordingSheet.closeKey));
    await tester.pumpAndSettle();
    expect(renamed, isEmpty);
    expect(result, isNull);
  });

  testWidgets('a failed rename shows the reason and keeps the sheet open', (
    tester,
  ) async {
    saved.complete({'failed_chunks': <Object?>[]});
    renameError = const SessionActionException(
      'The new name could not be saved. Try again.',
    );
    await openSheet(tester);
    await tester.enterText(find.byKey(SaveRecordingSheet.fieldKey), 'Notes');
    await tester.tap(find.byKey(SaveRecordingSheet.saveKey));
    await tester.pumpAndSettle();
    expect(
      find.text('The new name could not be saved. Try again.'),
      findsOneWidget,
    );
    expect(find.text(SaveRecordingSheet.title), findsOneWidget);
    expect(closed, isFalse);
  });

  testWidgets('a save with gaps is reported', (tester) async {
    saved.complete({
      'failed_chunks': <Object?>[3],
    });
    await openSheet(tester);
    expect(find.text('Saved on this phone, with a few gaps.'), findsOneWidget);
  });

  testWidgets('a quick name keeps the time and is saved', (tester) async {
    saved.complete({'failed_chunks': <Object?>[]});
    await openSheet(tester);
    await tester.tap(find.text('Meeting'));
    await tester.pump();
    expect(find.text('Meeting at 14:05'), findsOneWidget);
    await tester.tap(find.byKey(SaveRecordingSheet.saveKey));
    await tester.pumpAndSettle();
    expect(renamed, ['Meeting at 14:05']);
    expect(result, 'Meeting at 14:05');
  });

  test('suggested names', () {
    expect(
      SaveRecordingSheet.suggestedName('Lecture', 'Recording at 9:05'),
      'Lecture at 9:05',
    );
    expect(SaveRecordingSheet.suggestedName('Note', 'Recording'), 'Note');
  });
}
