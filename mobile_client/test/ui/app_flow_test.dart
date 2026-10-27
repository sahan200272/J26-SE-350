import 'dart:async';

import 'package:echo_vault/main.dart';
import 'package:echo_vault/sessions/session_store.dart';
import 'package:echo_vault/ui/app_shell.dart';
import 'package:echo_vault/ui/home_screen.dart';
import 'package:echo_vault/ui/onboarding_screen.dart';
import 'package:echo_vault/ui/onboarding_store.dart';
import 'package:echo_vault/ui/processing_privacy_screen.dart';
import 'package:echo_vault/ui/recording_screen.dart';
import 'package:echo_vault/ui/session_detail_screen.dart';
import 'package:echo_vault/ui/session_dialogs.dart';
import 'package:echo_vault/ui/sessions_screen.dart';
import 'package:echo_vault/ui/settings_home_screen.dart';
import 'package:echo_vault/ui/splash_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_audio_capture.dart';
import '../helpers/fake_microphone_permission.dart';
import '../helpers/fake_screen_awake.dart';
import '../helpers/pcm.dart';

class FakeSessionSource implements SessionSource {
  FakeSessionSource([this.sessions = const []]);

  List<SessionSummary> sessions;
  Completer<void>? gate;
  Object? error;
  int calls = 0;

  @override
  Future<List<SessionSummary>> list() async {
    calls++;
    if (gate case final g?) await g.future;
    if (error case final e?) throw e;
    return sessions;
  }

  /// When set, rename and delete throw it.
  Object? actionError;
  final renamed = <String, String>{};
  final deleted = <String>[];

  @override
  Future<void> rename(String id, String title) async {
    if (actionError case final e?) throw e;
    renamed[id] = title;
    sessions = [
      for (final s in sessions) s.id == id ? s.withTitle(title) : s,
    ];
  }

  @override
  Future<void> delete(String id) async {
    if (actionError case final e?) throw e;
    deleted.add(id);
    sessions = [
      for (final s in sessions)
        if (s.id != id) s,
    ];
  }
}

final sampleSession = SessionSummary(
  id: '20261018T013925_2fc3',
  complete: true,
  start: DateTime(2026, 10, 18, 1, 39, 25),
  sessionEndMs: 35356,
  recordedMs: 28843,
  pauseCount: 1,
  vadType: 'energy',
  chunks: const [
    ChunkSummary(seq: 0, startMs: 588, endMs: 1772, opusBytes: 6404),
    ChunkSummary(seq: 1, startMs: 2764, endMs: 6476, opusBytes: 19833),
  ],
);

void main() {
  late FakeAudioCapture capture;

  setUp(() => capture = FakeAudioCapture());

  EchoVaultApp app({
    bool showSplash = false,
    OnboardingStore? onboarding,
    SessionSource? sessions,
  }) => EchoVaultApp(
    permission: FakeMicrophonePermission(),
    capture: capture,
    screenAwake: FakeScreenAwake(),
    showSplash: showSplash,
    onboardingStore: onboarding,
    sessions: sessions,
  );

  Finder navLabel(String label) => find.descendant(
    of: find.byKey(AppShell.navKey),
    matching: find.text(label),
  );

  Future<void> openTab(WidgetTester tester, String label) async {
    await tester.tap(navLabel(label));
    await tester.pumpAndSettle();
  }

  /// Scrolls Home to its end, so the Recent recordings card sits above the
  /// floating navigation bar (Home's content runs behind the bar).
  Future<void> scrollHomeToEnd(WidgetTester tester) async {
    await tester.drag(
      find.descendant(
        of: find.byType(HomeScreen),
        matching: find.byType(SingleChildScrollView),
      ),
      const Offset(0, -600),
    );
    await tester.pumpAndSettle();
  }

  group('launch', () {
    testWidgets('first run: splash, welcome screens, then Home', (
      tester,
    ) async {
      final store = MemoryOnboardingStore();
      await tester.pumpWidget(app(showSplash: true, onboarding: store));
      expect(find.byType(SplashScreen), findsOneWidget);
      expect(capture.calls, isEmpty, reason: 'nothing recorded at launch');

      await tester.pump(const Duration(milliseconds: 1600));
      await tester.pumpAndSettle();
      expect(find.text('Record on your terms'), findsOneWidget);

      await tester.tap(find.byKey(OnboardingScreen.nextKey));
      await tester.pumpAndSettle();
      expect(find.text('Private by design'), findsOneWidget);
      await tester.tap(find.byKey(OnboardingScreen.nextKey));
      await tester.pumpAndSettle();
      expect(find.text('Your PC does the heavy lifting'), findsOneWidget);
      expect(
        find.byKey(OnboardingScreen.laterKey),
        findsNothing,
        reason: 'no Connect your PC page without a PC link',
      );
      await tester.tap(find.byKey(OnboardingScreen.nextKey));
      await tester.pumpAndSettle();

      expect(find.byType(HomeScreen), findsOneWidget);
      expect(find.text('Capture what matters'), findsOneWidget);
      expect(store.complete, isTrue);
      expect(capture.calls, isEmpty);
    });

    testWidgets('welcome screens can be skipped', (tester) async {
      final store = MemoryOnboardingStore();
      await tester.pumpWidget(app(onboarding: store));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(OnboardingScreen.skipKey));
      await tester.pumpAndSettle();
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(store.complete, isTrue);
    });

    testWidgets('returning user goes straight to Home', (tester) async {
      await tester.pumpWidget(
        app(onboarding: MemoryOnboardingStore(complete: true)),
      );
      await tester.pumpAndSettle();
      expect(find.byType(OnboardingScreen), findsNothing);
      expect(find.byType(HomeScreen), findsOneWidget);
    });
  });

  group('navigation', () {
    testWidgets('exactly Home, Sessions, Settings', (tester) async {
      await tester.pumpWidget(app(sessions: FakeSessionSource()));
      await tester.pumpAndSettle();
      for (final label in ['Home', 'Sessions', 'Settings']) {
        expect(navLabel(label), findsOneWidget, reason: label);
      }
      for (final label in ['Knowledge', 'Assistant']) {
        expect(navLabel(label), findsNothing, reason: label);
      }
      expect(find.byType(NavigationDestination), findsNWidgets(3));

      await openTab(tester, 'Sessions');
      expect(find.byType(SessionsScreen), findsOneWidget);

      await openTab(tester, 'Settings');
      expect(find.byType(SettingsHomeScreen), findsOneWidget);

      await openTab(tester, 'Home');
      expect(find.text('Capture what matters'), findsOneWidget);
    });

    testWidgets('no Sessions tab without a session source', (tester) async {
      await tester.pumpWidget(app());
      expect(navLabel('Sessions'), findsNothing);
      expect(navLabel('Home'), findsOneWidget);
    });

    testWidgets('Home privacy chip opens Processing & privacy', (
      tester,
    ) async {
      await tester.pumpWidget(app());
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(HomeScreen.privacyKey));
      await tester.pumpAndSettle();
      expect(find.byType(ProcessingPrivacyScreen), findsOneWidget);
    });
  });

  group('recording', () {
    testWidgets('Start recording opens the recorder and starts; leaving is '
        'blocked until Stop; Done returns Home and refreshes', (
      tester,
    ) async {
      final sessions = FakeSessionSource();
      await tester.pumpWidget(app(sessions: sessions));
      await tester.pumpAndSettle();
      expect(capture.calls, isEmpty);

      await tester.tap(find.byKey(HomeScreen.startKey));
      await tester.pump(); // push
      await tester.pump(const Duration(milliseconds: 400)); // transition
      await tester.pump(); // auto start (permission)
      expect(find.byType(RecordingScreen), findsOneWidget);
      expect(capture.calls, ['start']);

      capture.emit(constantPcm(1280, 10));
      await tester.pump();
      expect(find.byType(RecordingIndicator), findsOneWidget);

      // System back while recording: refused, still recording.
      await tester.binding.handlePopRoute();
      await tester.pump();
      // Shown by the messenger on each scaffold in the route stack; the
      // covered route below is not visible on the phone.
      expect(find.text(RecordingScreen.leaveBlockedMessage), findsWidgets);
      expect(find.byType(RecordingIndicator), findsOneWidget);

      await tester.tap(find.byKey(const Key('stop-button')));
      await tester.pump();
      await tester.pump(const Duration(seconds: 5)); // snack bar times out
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('stopped-summary')), findsOneWidget);

      final before = sessions.calls;
      await tester.tap(find.byKey(RecordingScreen.doneKey));
      await tester.pumpAndSettle();
      expect(find.byType(RecordingScreen), findsNothing);
      expect(find.byType(HomeScreen), findsOneWidget);
      expect(sessions.calls, greaterThan(before), reason: 'refreshed');
    });
  });

  group('sessions', () {
    testWidgets('header has a "Record" button with a microphone', (
      tester,
    ) async {
      await tester.pumpWidget(
        app(sessions: FakeSessionSource([sampleSession])),
      );
      await openTab(tester, 'Sessions');
      final record = find.byKey(SessionsScreen.recordKey);
      expect(record, findsOneWidget);
      expect(
        find.descendant(of: record, matching: find.text('Record')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: record, matching: find.byIcon(Icons.mic_rounded)),
        findsOneWidget,
      );
      expect(find.byTooltip('New recording'), findsOneWidget);
    });

    testWidgets('loading, then empty state with a working Start action', (
      tester,
    ) async {
      final source = FakeSessionSource()..gate = Completer<void>();
      await tester.pumpWidget(app(sessions: source));
      await tester.tap(navLabel('Sessions'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(SessionsScreen.loadingKey), findsOneWidget);

      source.gate!.complete();
      await tester.pumpAndSettle();
      expect(find.byKey(SessionsScreen.emptyKey), findsOneWidget);
      expect(find.text('No recordings yet'), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(SessionsScreen.emptyKey),
          matching: find.text('Start recording'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('error state with retry', (tester) async {
      final source = FakeSessionSource()..error = Exception('disk');
      await tester.pumpWidget(app(sessions: source));
      await openTab(tester, 'Sessions');
      expect(find.byKey(SessionsScreen.errorKey), findsOneWidget);

      source.error = null;
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();
      expect(find.byKey(SessionsScreen.emptyKey), findsOneWidget);
    });

    testWidgets('list shows time, status and transcript availability; '
        'detail is honest about the transcript', (tester) async {
      await tester.pumpWidget(
        app(sessions: FakeSessionSource([sampleSession])),
      );
      await openTab(tester, 'Sessions');
      expect(find.text('Recording at 01:39'), findsOneWidget);
      expect(find.text('Saved'), findsOneWidget);
      expect(find.text(TranscriptAvailability.label), findsOneWidget);
      expect(find.textContaining('20261018T013925_2fc3'), findsNothing);

      await tester.tap(find.text('Recording at 01:39'));
      await tester.pumpAndSettle();
      expect(find.byType(SessionDetailScreen), findsOneWidget);
      expect(find.byKey(SessionDetailScreen.transcriptKey), findsOneWidget);
      expect(
        find.text('Transcript not available on this phone yet'),
        findsOneWidget,
      );

      // Technical details are collapsed until opened.
      final list = find.byType(Scrollable).first;
      await tester.scrollUntilVisible(
        find.byKey(SessionDetailScreen.technicalKey),
        200,
        scrollable: list,
      );
      expect(find.text('20261018T013925_2fc3'), findsNothing);
      await tester.tap(find.text('Technical details'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('20261018T013925_2fc3'),
        200,
        scrollable: list,
      );
      expect(find.text('20261018T013925_2fc3'), findsOneWidget);
    });

    testWidgets('Home shows recent recordings and See all opens Sessions', (
      tester,
    ) async {
      await tester.pumpWidget(
        app(sessions: FakeSessionSource([sampleSession])),
      );
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byKey(HomeScreen.recentKey),
          matching: find.text('Recording at 01:39'),
        ),
        findsOneWidget,
      );
      await tester.tap(find.text('See all'));
      await tester.pumpAndSettle();
      expect(find.byType(SessionsScreen), findsOneWidget);
    });

    testWidgets('Home shows only the three newest recordings; a tile opens '
        'its detail', (tester) async {
      SessionSummary at(int minute) => SessionSummary(
        id: '20261018T10${minute.toString().padLeft(2, '0')}00_aaaa',
        complete: true,
        start: DateTime(2026, 10, 18, 10, minute),
        recordedMs: 4000,
        chunks: const [],
      );
      // Newest first, as SessionSource.list() returns them.
      await tester.pumpWidget(
        app(sessions: FakeSessionSource([at(4), at(3), at(2), at(1)])),
      );
      await tester.pumpAndSettle();
      Finder inRecent(String text) => find.descendant(
        of: find.byKey(HomeScreen.recentKey),
        matching: find.text(text),
      );
      expect(inRecent('Recording at 10:04'), findsOneWidget);
      expect(inRecent('Recording at 10:03'), findsOneWidget);
      expect(inRecent('Recording at 10:02'), findsOneWidget);
      expect(inRecent('Recording at 10:01'), findsNothing);

      await scrollHomeToEnd(tester);
      await tester.tap(inRecent('Recording at 10:03'));
      await tester.pumpAndSettle();
      expect(find.byType(SessionDetailScreen), findsOneWidget);
    });

    testWidgets('Home: empty recent state; heading opens Sessions', (
      tester,
    ) async {
      await tester.pumpWidget(app(sessions: FakeSessionSource()));
      await tester.pumpAndSettle();
      expect(
        find.descendant(
          of: find.byKey(HomeScreen.recentKey),
          matching: find.textContaining('No recordings yet'),
        ),
        findsOneWidget,
      );
      await scrollHomeToEnd(tester);
      await tester.tap(find.text('Recent recordings'));
      await tester.pumpAndSettle();
      expect(find.byType(SessionsScreen), findsOneWidget);
    });

    testWidgets('Sessions: search and the Today / Older filter', (
      tester,
    ) async {
      final now = DateTime.now();
      final today = SessionSummary(
        id: '20261019T090000_bbbb',
        complete: true,
        start: DateTime(now.year, now.month, now.day, 9),
        recordedMs: 3000,
        chunks: const [],
        title: 'Standup notes',
      );
      await tester.pumpWidget(
        app(sessions: FakeSessionSource([today, sampleSession])),
      );
      await openTab(tester, 'Sessions');
      expect(find.text('Standup notes'), findsOneWidget);
      expect(find.text('Recording at 01:39'), findsOneWidget);

      await tester.tap(
        find.descendant(
          of: find.byKey(SessionsScreen.filterKey),
          matching: find.text('Today'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Standup notes'), findsOneWidget);
      expect(find.text('Recording at 01:39'), findsNothing);

      await tester.tap(find.text('Older'));
      await tester.pumpAndSettle();
      expect(find.text('Standup notes'), findsNothing);
      expect(find.text('Recording at 01:39'), findsOneWidget);

      await tester.tap(find.text('All'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(SessionsScreen.searchKey), 'zzz');
      await tester.pumpAndSettle();
      expect(find.byKey(SessionsScreen.noMatchKey), findsOneWidget);

      await tester.tap(find.byKey(SessionsScreen.clearSearchKey));
      await tester.pumpAndSettle();
      expect(find.byKey(SessionsScreen.noMatchKey), findsNothing);
      expect(find.text('Standup notes'), findsOneWidget);
      expect(find.text('Recording at 01:39'), findsOneWidget);
    });

    testWidgets('Sessions row menu renames with the existing dialog', (
      tester,
    ) async {
      final source = FakeSessionSource([sampleSession]);
      await tester.pumpWidget(app(sessions: source));
      await openTab(tester, 'Sessions');
      await tester.tap(find.byTooltip('More options for Recording at 01:39'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Rename'));
      await tester.pumpAndSettle();
      expect(find.byKey(SessionDialogKeys.rename), findsOneWidget);
      await tester.enterText(
        find.byKey(SessionDialogKeys.renameField),
        'Design review',
      );
      await tester.tap(find.byKey(SessionDialogKeys.save));
      await tester.pumpAndSettle();
      expect(source.renamed, {sampleSession.id: 'Design review'});
      expect(find.text('Design review'), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
    });
  });

  testWidgets('Processing & privacy keeps technical terms collapsed', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(home: ProcessingPrivacyScreen()),
    );
    await tester.pumpAndSettle();
    expect(find.text('You choose when to record'), findsOneWidget);
    expect(find.textContaining('Syncthing'), findsNothing);

    final list = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(
      find.byKey(ProcessingPrivacyScreen.technicalKey),
      200,
      scrollable: list,
    );
    await tester.tap(find.text('Technical details'));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.textContaining('Syncthing'),
      200,
      scrollable: list,
    );
    expect(find.textContaining('Syncthing'), findsOneWidget);
  });

  group('recording management', () {
    late FakeSessionSource source;

    Future<void> openDetail(WidgetTester tester) async {
      source = FakeSessionSource([sampleSession]);
      await tester.pumpWidget(app(sessions: source));
      await openTab(tester, 'Sessions');
      await tester.tap(find.text('Recording at 01:39'));
      await tester.pumpAndSettle();
      expect(find.byType(SessionDetailScreen), findsOneWidget);
    }

    Future<void> chooseMenu(WidgetTester tester, Key item) async {
      await tester.tap(find.byKey(SessionDetailScreen.menuKey));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(item));
      await tester.pumpAndSettle();
    }

    String titleText(WidgetTester tester) =>
        tester.widget<Text>(find.byKey(SessionDetailScreen.titleKey)).data!;

    testWidgets('rename: trimmed title shown in detail and in the list', (
      tester,
    ) async {
      await openDetail(tester);
      await chooseMenu(tester, SessionDetailScreen.renameItemKey);
      expect(find.byKey(SessionDialogKeys.rename), findsOneWidget);

      await tester.enterText(
        find.byKey(SessionDialogKeys.renameField),
        '  Weekly   project sync  ',
      );
      await tester.tap(find.byKey(SessionDialogKeys.save));
      await tester.pumpAndSettle();

      expect(find.byKey(SessionDialogKeys.rename), findsNothing);
      expect(source.renamed, {sampleSession.id: 'Weekly project sync'});
      expect(titleText(tester), 'Weekly project sync');

      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.text('Weekly project sync'), findsOneWidget);
      expect(find.text('Recording at 01:39'), findsNothing);
      await tester.pump(const Duration(seconds: 5));
    });

    testWidgets('rename: empty title is rejected; Cancel changes nothing', (
      tester,
    ) async {
      await openDetail(tester);
      await chooseMenu(tester, SessionDetailScreen.renameItemKey);
      await tester.enterText(find.byKey(SessionDialogKeys.renameField), '   ');
      await tester.tap(find.byKey(SessionDialogKeys.save));
      await tester.pumpAndSettle();
      expect(find.text('Enter a name for the recording.'), findsOneWidget);
      expect(find.byKey(SessionDialogKeys.rename), findsOneWidget);

      await tester.tap(find.byKey(SessionDialogKeys.cancel));
      await tester.pumpAndSettle();
      expect(find.byKey(SessionDialogKeys.rename), findsNothing);
      expect(source.renamed, isEmpty);
      expect(titleText(tester), 'Recording at 01:39');
    });

    testWidgets('rename failure is reported and the title is unchanged', (
      tester,
    ) async {
      await openDetail(tester);
      source.actionError = const SessionActionException(
        'The new name could not be saved. Try again.',
      );
      await chooseMenu(tester, SessionDetailScreen.renameItemKey);
      await tester.enterText(
        find.byKey(SessionDialogKeys.renameField),
        'New name',
      );
      await tester.tap(find.byKey(SessionDialogKeys.save));
      await tester.pumpAndSettle();
      expect(
        find.text('The new name could not be saved. Try again.'),
        findsOneWidget,
      );
      expect(titleText(tester), 'Recording at 01:39');
      await tester.pump(const Duration(seconds: 5));
    });

    testWidgets('delete: Cancel keeps the recording', (tester) async {
      await openDetail(tester);
      await chooseMenu(tester, SessionDetailScreen.deleteItemKey);
      expect(find.byKey(SessionDialogKeys.delete), findsOneWidget);
      expect(
        find.textContaining('If it was already sent to your PC'),
        findsOneWidget,
      );

      await tester.tap(find.byKey(SessionDialogKeys.cancel));
      await tester.pumpAndSettle();
      expect(source.deleted, isEmpty);
      expect(find.byType(SessionDetailScreen), findsOneWidget);
    });

    testWidgets('delete: confirmed, list updates only after success', (
      tester,
    ) async {
      await openDetail(tester);
      await chooseMenu(tester, SessionDetailScreen.deleteItemKey);
      await tester.tap(find.byKey(SessionDialogKeys.confirmDelete));
      await tester.pumpAndSettle();

      expect(source.deleted, [sampleSession.id]);
      expect(find.byType(SessionDetailScreen), findsNothing);
      expect(find.text(SessionDetailScreen.deletedMessage), findsOneWidget);
      expect(find.byKey(SessionsScreen.emptyKey), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
    });

    testWidgets('delete failure: message shown, recording kept', (
      tester,
    ) async {
      await openDetail(tester);
      source.actionError = const SessionActionException(
        'The recording was not deleted: the copy on your PC could not be '
        'protected. Try again.',
      );
      await chooseMenu(tester, SessionDetailScreen.deleteItemKey);
      await tester.tap(find.byKey(SessionDialogKeys.confirmDelete));
      await tester.pumpAndSettle();

      expect(find.byType(SessionDetailScreen), findsOneWidget);
      expect(
        find.textContaining('could not be protected'),
        findsOneWidget,
      );
      expect(source.sessions, hasLength(1));
      await tester.pump(const Duration(seconds: 5));
    });
  });
}
