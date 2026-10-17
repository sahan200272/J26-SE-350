import 'dart:async';

import 'package:echo_vault/permissions/microphone_permission.dart';
import 'package:echo_vault/ui/recording_controller.dart';
import 'package:echo_vault/ui/recording_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_clock.dart';
import '../helpers/fake_microphone_permission.dart';

final startButton = find.byKey(const Key('start-button'));
final pauseResumeButton = find.byKey(const Key('pause-resume-button'));
final stopButton = find.byKey(const Key('stop-button'));
final indicator = find.byType(RecordingIndicator);
final pausedIndicator = find.byType(PausedIndicator);
final redDot = find.byKey(RecordingIndicator.dotKey);
final permissionMessage = find.byKey(const Key('permission-message'));

bool isEnabled(WidgetTester tester, Finder button) =>
    tester.widget<ButtonStyleButton>(button).onPressed != null;

/// Expected (start, pause/resume, stop) enabled states.
void expectButtons(
  WidgetTester tester, {
  required bool start,
  required bool pauseResume,
  required bool stop,
}) {
  expect(isEnabled(tester, startButton), start, reason: 'Start');
  expect(
    isEnabled(tester, pauseResumeButton),
    pauseResume,
    reason: 'Pause/Resume',
  );
  expect(isEnabled(tester, stopButton), stop, reason: 'Stop');
}

void expectRecordingIndicatorVisible(bool visible) {
  final m = visible ? findsOneWidget : findsNothing;
  expect(indicator, m);
  expect(redDot, m);
  expect(find.text('Recording'), m);
  expect(find.byKey(RecordingIndicator.timerKey), m);
}

void main() {
  late FakeClock clock;
  late FakeMicrophonePermission permission;

  setUp(() {
    clock = FakeClock();
    permission = FakeMicrophonePermission();
  });

  Future<void> pumpScreen(WidgetTester tester) => tester.pumpWidget(
    MaterialApp(
      home: RecordingScreen(permission: permission, clock: clock),
    ),
  );

  Future<void> tap(WidgetTester tester, Finder f) async {
    await tester.tap(f);
    await tester.pump();
  }

  testWidgets('idle: no indicator; only Start enabled', (tester) async {
    await pumpScreen(tester);
    expectRecordingIndicatorVisible(false);
    expect(pausedIndicator, findsNothing);
    expect(find.text('Ready to record'), findsOneWidget);
    expect(find.text('Pause'), findsOneWidget);
    expectButtons(tester, start: true, pauseResume: false, stop: false);
    expect(permission.requestCount, 0, reason: 'no request before Start');
  });

  testWidgets('Start (granted): indicator shown; Pause and Stop enabled', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tap(tester, startButton);

    expect(permission.requestCount, 1);
    expectRecordingIndicatorVisible(true);
    expect(find.text('00:00'), findsOneWidget);
    expect(
      tester.widget<Container>(redDot).decoration,
      isA<BoxDecoration>().having((d) => d.color, 'color', Colors.red),
    );
    expect(pausedIndicator, findsNothing);
    expectButtons(tester, start: false, pauseResume: true, stop: true);
  });

  testWidgets('timer advances while recording', (tester) async {
    await pumpScreen(tester);
    await tap(tester, startButton);

    clock.advance(const Duration(seconds: 65));
    await tester.pump(const Duration(milliseconds: 250)); // ticker fires
    expect(find.text('01:05'), findsOneWidget);
  });

  testWidgets('Pause: indicator hidden, distinct Paused display, Resume', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tap(tester, startButton);
    clock.advance(const Duration(seconds: 3));
    await tap(tester, pauseResumeButton);

    expectRecordingIndicatorVisible(false);
    expect(pausedIndicator, findsOneWidget);
    expect(find.text('Paused'), findsOneWidget);
    expect(find.text('Resume'), findsOneWidget);
    expect(find.byIcon(Icons.pause_circle_filled), findsOneWidget);
    expectButtons(tester, start: false, pauseResume: true, stop: true);

    // Paused time is not counted.
    clock.advance(const Duration(seconds: 20));
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('00:03'), findsOneWidget);
  });

  testWidgets('Resume: indicator back, paused time excluded', (tester) async {
    await pumpScreen(tester);
    await tap(tester, startButton);
    clock.advance(const Duration(seconds: 3));
    await tap(tester, pauseResumeButton); // pause
    clock.advance(const Duration(seconds: 20));
    await tap(tester, pauseResumeButton); // resume
    clock.advance(const Duration(seconds: 2));
    await tester.pump(const Duration(milliseconds: 250));

    expectRecordingIndicatorVisible(true);
    expect(pausedIndicator, findsNothing);
    expect(find.text('Pause'), findsOneWidget);
    expect(find.text('00:05'), findsOneWidget);
    expectButtons(tester, start: false, pauseResume: true, stop: true);
  });

  testWidgets('Stop from recording: no indicator; only Start enabled', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tap(tester, startButton);
    clock.advance(const Duration(seconds: 4));
    await tap(tester, stopButton);

    expectRecordingIndicatorVisible(false);
    expect(pausedIndicator, findsNothing);
    expect(find.text('Stopped'), findsOneWidget);
    expect(find.text('Recorded 00:04 · 0 pauses'), findsOneWidget);
    expectButtons(tester, start: true, pauseResume: false, stop: false);
  });

  testWidgets('Stop from paused: no indicator; only Start enabled', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tap(tester, startButton);
    clock.advance(const Duration(seconds: 2));
    await tap(tester, pauseResumeButton);
    clock.advance(const Duration(seconds: 9));
    await tap(tester, stopButton);

    expectRecordingIndicatorVisible(false);
    expect(pausedIndicator, findsNothing);
    expect(find.text('Recorded 00:02 · 1 pause'), findsOneWidget);
    expectButtons(tester, start: true, pauseResume: false, stop: false);
  });

  testWidgets('Start after Stop begins a new session from 00:00', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tap(tester, startButton);
    clock.advance(const Duration(seconds: 9));
    await tap(tester, stopButton);
    await tap(tester, startButton);

    expect(permission.requestCount, 2);
    expectRecordingIndicatorVisible(true);
    expect(find.text('00:00'), findsOneWidget);
  });

  group('permission not granted', () {
    testWidgets('denied: message shown, stays idle, no indicator', (
      tester,
    ) async {
      permission.status = MicPermissionStatus.denied;
      await pumpScreen(tester);
      await tap(tester, startButton);

      expect(permissionMessage, findsOneWidget);
      expect(find.text(RecordingController.deniedMessage), findsOneWidget);
      expectRecordingIndicatorVisible(false);
      expect(pausedIndicator, findsNothing);
      expect(find.text('Ready to record'), findsOneWidget);
      expectButtons(tester, start: true, pauseResume: false, stop: false);
    });

    testWidgets('permanently denied: settings message shown, stays idle', (
      tester,
    ) async {
      permission.status = MicPermissionStatus.permanentlyDenied;
      await pumpScreen(tester);
      await tap(tester, startButton);

      expect(
        find.text(RecordingController.permanentlyDeniedMessage),
        findsOneWidget,
      );
      expectRecordingIndicatorVisible(false);
      expectButtons(tester, start: true, pauseResume: false, stop: false);
    });

    testWidgets('platform error is treated as denied', (tester) async {
      permission.error = PlatformException(code: 'IN_PROGRESS');
      await pumpScreen(tester);
      await tap(tester, startButton);

      expect(find.text(RecordingController.deniedMessage), findsOneWidget);
      expectRecordingIndicatorVisible(false);
    });

    testWidgets('message clears when a later Start is granted', (tester) async {
      permission.status = MicPermissionStatus.denied;
      await pumpScreen(tester);
      await tap(tester, startButton);
      expect(permissionMessage, findsOneWidget);

      permission.status = MicPermissionStatus.granted;
      await tap(tester, startButton);
      expect(permissionMessage, findsNothing);
      expectRecordingIndicatorVisible(true);
    });
  });

  testWidgets('all buttons disabled while the permission dialog is open', (
    tester,
  ) async {
    final pending = Completer<MicPermissionStatus>();
    permission.completer = pending;
    await pumpScreen(tester);
    await tap(tester, startButton);

    expect(find.text('Requesting microphone access…'), findsOneWidget);
    expectRecordingIndicatorVisible(false);
    expectButtons(tester, start: false, pauseResume: false, stop: false);

    pending.complete(MicPermissionStatus.granted);
    await tester.pump();
    expectRecordingIndicatorVisible(true);
  });

  group('control labels stay on one line on a 360 dp wide screen', () {
    void useNarrowPhone(WidgetTester tester) {
      tester.view
        ..devicePixelRatio = 1.0
        ..physicalSize = const Size(360, 800);
      addTearDown(tester.view.reset);
    }

    /// Each label: exactly one line, not truncated, fully inside its button.
    void expectSingleLineLabels(
      WidgetTester tester,
      Map<String, Finder> buttonsByLabel,
    ) {
      expect(tester.getSize(find.byType(RecordingScreen)).width, 360);
      for (final MapEntry(key: label, value: button)
          in buttonsByLabel.entries) {
        final text = find.descendant(of: button, matching: find.text(label));
        expect(text, findsOneWidget, reason: label);

        // One distinct box top per laid-out line.
        final paragraph = tester.renderObject<RenderParagraph>(text);
        final lineTops = paragraph
            .getBoxesForSelection(
              TextSelection(baseOffset: 0, extentOffset: label.length),
            )
            .map((box) => box.top)
            .toSet();
        expect(lineTops, hasLength(1), reason: '"$label" wrapped');
        expect(
          paragraph.didExceedMaxLines,
          isFalse,
          reason: '"$label" truncated',
        );

        final buttonRect = tester.getRect(button);
        expect(
          buttonRect.expandToInclude(tester.getRect(text)),
          buttonRect,
          reason: '"$label" overflows its button',
        );
      }
    }

    testWidgets('recording: Start / Pause / Stop', (tester) async {
      useNarrowPhone(tester);
      await pumpScreen(tester);
      await tap(tester, startButton);

      expectSingleLineLabels(tester, {
        'Start': startButton,
        'Pause': pauseResumeButton,
        'Stop': stopButton,
      });
    });

    testWidgets('paused: Start / Resume / Stop', (tester) async {
      useNarrowPhone(tester);
      await pumpScreen(tester);
      await tap(tester, startButton);
      await tap(tester, pauseResumeButton);

      expectSingleLineLabels(tester, {
        'Start': startButton,
        'Resume': pauseResumeButton,
        'Stop': stopButton,
      });
    });
  });
}
