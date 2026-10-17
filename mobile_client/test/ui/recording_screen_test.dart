import 'dart:async';

import 'package:echo_vault/capture/audio_capture.dart';
import 'package:echo_vault/permissions/microphone_permission.dart';
import 'package:echo_vault/ui/input_level_meter.dart';
import 'package:echo_vault/ui/lifecycle_source.dart';
import 'package:echo_vault/ui/recording_controller.dart';
import 'package:echo_vault/ui/recording_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_audio_capture.dart';
import '../helpers/fake_clock.dart';
import '../helpers/fake_lifecycle.dart';
import '../helpers/fake_microphone_permission.dart';
import '../helpers/fake_random.dart';
import '../helpers/fake_screen_awake.dart';
import '../helpers/pcm.dart';

final startButton = find.byKey(const Key('start-button'));
final pauseResumeButton = find.byKey(const Key('pause-resume-button'));
final stopButton = find.byKey(const Key('stop-button'));
final indicator = find.byType(RecordingIndicator);
final pausedIndicator = find.byType(PausedIndicator);
final redDot = find.byKey(RecordingIndicator.dotKey);
final permissionMessage = find.byKey(const Key('permission-message'));
final levelMeter = find.byType(InputLevelMeter);
final levelValue = find.byKey(InputLevelMeter.valueKey);
final autoPauseNotice = find.byKey(const Key('auto-pause-notice'));

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
  late FakeAudioCapture capture;
  late FakeScreenAwake screen;
  late FakeLifecycle lifecycle;

  setUp(() {
    clock = FakeClock();
    permission = FakeMicrophonePermission();
    capture = FakeAudioCapture();
    screen = FakeScreenAwake();
    lifecycle = FakeLifecycle();
  });

  Future<void> pumpScreen(
    WidgetTester tester, {
    LifecycleSource? lifecycleSource,
  }) => tester.pumpWidget(
    MaterialApp(
      home: RecordingScreen(
        permission: permission,
        capture: capture,
        screenAwake: screen,
        lifecycle: lifecycleSource ?? lifecycle,
        clock: clock,
        wallClock: () => DateTime(2026, 10, 15, 14, 23, 0),
        random: FakeRandom(0xa1b2),
      ),
    ),
  );

  Future<void> tap(WidgetTester tester, Finder f) async {
    await tester.tap(f);
    await tester.pump();
  }

  /// The run's first audio arrives (a quiet chunk the VAD calls silence).
  Future<void> feedAudio(WidgetTester tester) async {
    capture.emit(constantPcm(1280, 10));
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

  testWidgets('Start (granted): "Starting microphone…" without the red dot '
      'until the first audio, then the indicator; Pause and Stop enabled', (
    tester,
  ) async {
    await pumpScreen(tester);
    await tap(tester, startButton);

    expect(permission.requestCount, 1);
    expect(find.byType(StartingIndicator), findsOneWidget);
    expect(find.text(StartingIndicator.label), findsOneWidget);
    expectRecordingIndicatorVisible(false);
    expect(levelMeter, findsNothing);
    expectButtons(tester, start: false, pauseResume: true, stop: true);

    await feedAudio(tester);
    expect(find.byType(StartingIndicator), findsNothing);
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
    expect(find.byType(StartingIndicator), findsOneWidget);
    expectRecordingIndicatorVisible(false);
    await feedAudio(tester);
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
    await feedAudio(tester);

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
      await feedAudio(tester);
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
    await feedAudio(tester);
    expectRecordingIndicatorVisible(true);
  });

  group('capture wiring', () {
    testWidgets('Start/Pause/Resume/Stop drive the capture and the screen '
        'wake flag', (tester) async {
      await pumpScreen(tester);
      await tap(tester, startButton);
      expect(capture.calls, ['start']);
      expect(screen.calls, [true]);
      await tap(tester, pauseResumeButton);
      await tap(tester, pauseResumeButton);
      expect(capture.calls, ['start', 'pause', 'resume']);
      expect(screen.calls, [true], reason: 'stays on while paused');
      await tap(tester, stopButton);
      expect(capture.calls, ['start', 'pause', 'resume', 'stop']);
      expect(screen.calls, [true, false]);
    });

    testWidgets('Stop shows the session ID', (tester) async {
      await pumpScreen(tester);
      await tap(tester, startButton);
      await tap(tester, stopButton);
      expect(find.text('Session 20261015T142300_a1b2'), findsOneWidget);
    });

    testWidgets('capture failure: stopped, message shown', (tester) async {
      capture.errors['start'] = const CaptureFailure('mic busy');
      await pumpScreen(tester);
      await tap(tester, startButton);
      await tester.pump();
      expect(find.text('Stopped'), findsOneWidget);
      expect(
        find.text(
          RecordingController.captureFailedMessage(
            const CaptureFailure('mic busy'),
          ),
        ),
        findsOneWidget,
      );
      expectRecordingIndicatorVisible(false);
    });
  });

  group('input level meter', () {
    testWidgets('shown only while recording, with the RMS level in dBFS', (
      tester,
    ) async {
      await pumpScreen(tester);
      expect(levelMeter, findsNothing);

      await tap(tester, startButton);
      expect(levelMeter, findsNothing, reason: 'starting microphone');

      capture.emit(constantPcm(1536, 3277)); // 3 frames, ≈ −20 dBFS
      await tester.pump();
      expect(levelMeter, findsOneWidget);
      expect(tester.widget<Text>(levelValue).data, '– dBFS');
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.widget<Text>(levelValue).data, '-20.0 dBFS');
      final bar = tester.widget<LinearProgressIndicator>(
        find.byKey(InputLevelMeter.barKey),
      );
      expect(bar.value, closeTo(40 / 60, 1e-3));

      capture.emit(constantPcm(1536, 0)); // digital silence
      await tester.pump(const Duration(milliseconds: 100));
      expect(tester.widget<Text>(levelValue).data, '-96.0 dBFS');

      await tap(tester, pauseResumeButton);
      expect(levelMeter, findsNothing);
      await tap(tester, pauseResumeButton);
      expect(levelMeter, findsNothing, reason: 'starting microphone');
      await feedAudio(tester);
      expect(levelMeter, findsOneWidget);
      expect(
        tester.widget<Text>(levelValue).data,
        '– dBFS',
        reason: 'no stale level after resume',
      );
      await tap(tester, stopButton);
      expect(levelMeter, findsNothing);
    });

    test('bar fraction and text formatting', () {
      expect(InputLevelMeter.fraction(null), 0);
      expect(InputLevelMeter.fraction(-96), 0);
      expect(InputLevelMeter.fraction(-30), 0.5);
      expect(InputLevelMeter.fraction(0), 1);
      expect(InputLevelMeter.format(-3.04), '-3.0 dBFS');
    });
  });

  group('speech indicator and segment count', () {
    final listening = find.byKey(SpeechStatus.listeningKey);
    final speech = find.byKey(SpeechStatus.speechKey);
    final count = find.byKey(SpeechStatus.countKey);

    testWidgets('"Speech detected" during speech; count rises when the '
        'segment ends; summary after Stop', (tester) async {
      await pumpScreen(tester);
      await tap(tester, startButton);
      expect(listening, findsNothing, reason: 'starting microphone');

      capture.emit(constantPcm(512 * 20, 0)); // 20 frames of silence
      await tester.pump();
      expect(listening, findsOneWidget);
      expect(speech, findsNothing);
      expect(tester.widget<Text>(count).data, 'Segments: 0');

      capture.emit(constantPcm(512 * 31, 3277)); // ≈ 1 s at −20 dBFS
      await tester.pump();
      expect(speech, findsOneWidget);
      expect(find.text('Speech detected'), findsOneWidget);
      expect(tester.widget<Text>(count).data, 'Segments: 0');

      capture.emit(constantPcm(512 * 25, 0)); // hangover ends the segment
      await tester.pump();
      expect(listening, findsOneWidget);
      expect(tester.widget<Text>(count).data, 'Segments: 1');

      await tap(tester, stopButton);
      expect(find.text('1 speech segment'), findsOneWidget);
    });

    testWidgets('not shown while starting or paused', (tester) async {
      await pumpScreen(tester);
      await tap(tester, startButton);
      expect(find.byType(SpeechStatus), findsNothing);
      await feedAudio(tester);
      expect(find.byType(SpeechStatus), findsOneWidget);
      await tap(tester, pauseResumeButton);
      expect(find.byType(SpeechStatus), findsNothing);
    });
  });

  group('auto-pause when the app leaves the foreground', () {
    testWidgets('hidden: "Paused automatically" notice; resumes only on tap', (
      tester,
    ) async {
      await pumpScreen(tester);
      await tap(tester, startButton);
      lifecycle
        ..emit(AppLifecycleState.inactive)
        ..emit(AppLifecycleState.hidden);
      await tester.pump();

      expect(pausedIndicator, findsOneWidget);
      expect(autoPauseNotice, findsOneWidget);
      expect(find.text('Paused automatically'), findsOneWidget);
      expect(capture.calls, ['start', 'pause']);

      lifecycle
        ..emit(AppLifecycleState.inactive)
        ..emit(AppLifecycleState.resumed);
      await tester.pump(const Duration(seconds: 1));
      expect(pausedIndicator, findsOneWidget, reason: 'no auto-resume');

      await tap(tester, pauseResumeButton);
      await feedAudio(tester);
      expectRecordingIndicatorVisible(true);
      expect(autoPauseNotice, findsNothing);
    });

    testWidgets('a user pause shows no notice', (tester) async {
      await pumpScreen(tester);
      await tap(tester, startButton);
      await tap(tester, pauseResumeButton);
      expect(pausedIndicator, findsOneWidget);
      expect(autoPauseNotice, findsNothing);
    });

    testWidgets('real AppLifecycleListener: binding lifecycle events pause', (
      tester,
    ) async {
      await pumpScreen(tester, lifecycleSource: const AppLifecycleSource());
      await tap(tester, startButton);
      await feedAudio(tester);
      final binding = tester.binding;
      binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      await tester.pump();
      expectRecordingIndicatorVisible(true);

      binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
      await tester.pump();
      expect(autoPauseNotice, findsOneWidget);
      expect(capture.calls, ['start', 'pause']);

      binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(autoPauseNotice, findsOneWidget);
    });
  });

  group('control labels stay on one line on narrow phones', () {
    /// (name, physical size, device pixel ratio, text scale, width in dp)
    const screens = [
      ('360 dp', Size(360, 800), 1.0, 1.0, 360.0),
      // Samsung Galaxy A06 (SM-A065F) as read with `adb shell wm size` /
      // `wm density`: 720×1600 px at 300 dpi → DPR 1.875, 384 dp wide.
      ('Galaxy A06 (384 dp)', Size(720, 1600), 1.875, 1.0, 384.0),
      ('360 dp, text ×1.3', Size(360, 800), 1.0, 1.3, 360.0),
    ];

    void useScreen(
      WidgetTester tester,
      Size physicalSize,
      double devicePixelRatio,
      double textScale,
    ) {
      tester.view
        ..devicePixelRatio = devicePixelRatio
        ..physicalSize = physicalSize;
      tester.platformDispatcher.textScaleFactorTestValue = textScale;
      addTearDown(tester.view.reset);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    }

    /// Each label: exactly one line, not truncated, fully inside its button.
    void expectSingleLineLabels(
      WidgetTester tester,
      double widthDp,
      Map<String, Finder> buttonsByLabel,
    ) {
      expect(tester.getSize(find.byType(RecordingScreen)).width, widthDp);
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

    for (final (name, size, dpr, textScale, widthDp) in screens) {
      testWidgets('$name, idle: Start / Pause / Stop', (tester) async {
        useScreen(tester, size, dpr, textScale);
        await pumpScreen(tester);

        expectSingleLineLabels(tester, widthDp, {
          'Start': startButton,
          'Pause': pauseResumeButton,
          'Stop': stopButton,
        });
      });

      testWidgets('$name, recording: Start / Pause / Stop', (tester) async {
        useScreen(tester, size, dpr, textScale);
        await pumpScreen(tester);
        await tap(tester, startButton);

        expectSingleLineLabels(tester, widthDp, {
          'Start': startButton,
          'Pause': pauseResumeButton,
          'Stop': stopButton,
        });
      });

      testWidgets('$name, paused: Start / Resume / Stop', (tester) async {
        useScreen(tester, size, dpr, textScale);
        await pumpScreen(tester);
        await tap(tester, startButton);
        await tap(tester, pauseResumeButton);

        expectSingleLineLabels(tester, widthDp, {
          'Start': startButton,
          'Resume': pauseResumeButton,
          'Stop': stopButton,
        });
      });
    }
  });
}
