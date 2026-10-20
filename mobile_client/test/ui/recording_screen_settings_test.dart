import 'package:echo_vault/ui/recording_screen.dart';
import 'package:echo_vault/ui/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_audio_capture.dart';
import '../helpers/fake_clock.dart';
import '../helpers/fake_lifecycle.dart';
import '../helpers/fake_microphone_permission.dart';
import '../helpers/fake_random.dart';
import '../helpers/fake_screen_awake.dart';
import '../helpers/fake_syncthing_client.dart';
import '../helpers/pcm.dart';

final settingsButton = find.byKey(RecordingScreen.settingsKey);

void main() {
  late FakeAudioCapture capture;

  setUp(() => capture = FakeAudioCapture());

  Future<void> pumpScreen(WidgetTester tester, {bool withSyncthing = true}) =>
      tester.pumpWidget(
        MaterialApp(
          home: RecordingScreen(
            permission: FakeMicrophonePermission(),
            capture: capture,
            screenAwake: FakeScreenAwake(),
            lifecycle: FakeLifecycle(),
            clock: FakeClock(),
            wallClock: () => DateTime(2026, 10, 18, 10),
            random: FakeRandom(0xa1b2),
            syncthing: withSyncthing ? FakeSyncthingClient() : null,
            doubleTapGuard: Duration.zero,
          ),
        ),
      );

  bool enabled(WidgetTester tester) =>
      tester.widget<IconButton>(settingsButton).onPressed != null;

  Future<void> tapKey(WidgetTester tester, String key) async {
    await tester.tap(find.byKey(Key(key)));
    await tester.pump();
  }

  testWidgets('no settings button without a Syncthing client', (tester) async {
    await pumpScreen(tester, withSyncthing: false);
    expect(settingsButton, findsNothing);
  });

  testWidgets('settings only between sessions, so the recording indicator '
      'stays visible while a session is open (FR1)', (tester) async {
    await pumpScreen(tester);
    expect(enabled(tester), isTrue, reason: 'idle');

    await tapKey(tester, 'start-button');
    capture.emit(constantPcm(1280, 10));
    await tester.pump();
    expect(find.byType(RecordingIndicator), findsOneWidget);
    expect(enabled(tester), isFalse, reason: 'recording');

    await tapKey(tester, 'pause-resume-button');
    expect(enabled(tester), isFalse, reason: 'paused');

    await tapKey(tester, 'stop-button');
    await tester.pump();
    expect(find.byKey(const Key('stopped-summary')), findsOneWidget);
    expect(enabled(tester), isTrue, reason: 'stopped');
  });

  testWidgets('the button opens the sync settings', (tester) async {
    await pumpScreen(tester);
    await tester.tap(settingsButton);
    await tester.pumpAndSettle();
    expect(find.byType(SettingsScreen), findsOneWidget);
    // Leave the screen so its poll timer is cancelled.
    await tester.pageBack();
    await tester.pumpAndSettle();
  });
}
