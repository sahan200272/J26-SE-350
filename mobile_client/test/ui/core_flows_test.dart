import 'package:echo_vault/sessions/session_store.dart';
import 'package:echo_vault/ui/home_screen.dart';
import 'package:echo_vault/ui/session_detail_screen.dart';
import 'package:echo_vault/ui/settings_home_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_syncthing_client.dart';

/// Lists [sessions], or throws [error] when set.
class _Source implements SessionSource {
  _Source(this.sessions);

  List<SessionSummary> sessions;
  Object? error;

  @override
  Future<List<SessionSummary>> list() async {
    if (error case final e?) throw e;
    return sessions;
  }

  @override
  Future<void> rename(String id, String title) async {}

  @override
  Future<void> delete(String id) async {}
}

void main() {
  SessionSummary session({int failedChunks = 0}) => SessionSummary(
    id: '20261018T013925_2fc3',
    complete: true,
    start: DateTime(2026, 10, 18, 1, 39, 25),
    sessionEndMs: 35356,
    recordedMs: 28843,
    failedChunks: failedChunks,
    chunks: const [
      ChunkSummary(seq: 0, startMs: 588, endMs: 1772, opusBytes: 6404),
    ],
  );

  group('Recording detail', () {
    testWidgets('a recording saved with gaps says what that means', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: SessionDetailScreen(session: session(failedChunks: 2))),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(SessionDetailScreen.gapsKey), findsOneWidget);
      expect(find.textContaining('2 short parts could not be stored'), findsOneWidget);
    });

    testWidgets('a complete recording has no gaps notice; the figures are '
        'explained', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: SessionDetailScreen(session: session())),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(SessionDetailScreen.gapsKey), findsNothing);
      await tester.scrollUntilVisible(
        find.byKey(SessionDetailScreen.statsHelpKey),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.textContaining('Parts are the stretches of speech'), findsOneWidget);
    });
  });

  group('Settings', () {
    testWidgets('Microphone access opens Android Settings', (tester) async {
      var opened = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: SettingsHomeScreen(
            openSettings: () async {
              opened++;
              return true;
            },
          ),
        ),
      );
      await tester.tap(find.byKey(SettingsHomeScreen.micRowKey));
      await tester.pump();
      expect(opened, 1);
      expect(find.text(SettingsHomeScreen.openSettingsFailedMessage), findsNothing);
    });

    testWidgets('says where to go when Android Settings cannot be opened', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: SettingsHomeScreen(openSettings: () async => false),
        ),
      );
      await tester.tap(find.byKey(SettingsHomeScreen.micRowKey));
      await tester.pump();
      await tester.pump();
      expect(
        find.text(SettingsHomeScreen.openSettingsFailedMessage),
        findsOneWidget,
      );
    });

    testWidgets('About shows the version', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: SettingsHomeScreen(appVersion: Future.value('1.0.0+1')),
        ),
      );
      await tester.pump();
      expect(
        find.text('Version 1.0.0+1 · open-source licences'),
        findsOneWidget,
      );
    });
  });

  group('Home', () {
    testWidgets('recent recordings that failed to load can be retried', (
      tester,
    ) async {
      final source = _Source([session()])..error = Exception('disk');
      await tester.pumpWidget(MaterialApp(home: HomeScreen(sessions: source)));
      await tester.pumpAndSettle();
      expect(find.byKey(HomeScreen.retryKey), findsOneWidget);

      source.error = null;
      await tester.ensureVisible(find.byKey(HomeScreen.retryKey));
      await tester.tap(find.byKey(HomeScreen.retryKey));
      await tester.pumpAndSettle();
      expect(find.byKey(HomeScreen.retryKey), findsNothing);
      expect(find.text('Recording at 01:39'), findsOneWidget);
    });
  });

  group('Recording detail: is it on the PC?', () {
    Future<void> pumpDetail(WidgetTester tester, int? pending) async {
      final client = FakeSyncthingClient()..pendingForSession = pending;
      await tester.pumpWidget(
        MaterialApp(
          home: SessionDetailScreen(session: session(), syncthing: client),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('every file sent: "On your PC"', (tester) async {
      await pumpDetail(tester, 0);
      expect(find.text('On your PC'), findsOneWidget);
    });

    testWidgets('files waiting: "Waiting to send to your PC"', (tester) async {
      await pumpDetail(tester, 3);
      expect(find.text('Waiting to send to your PC'), findsOneWidget);
    });

    testWidgets('unknown: no chip', (tester) async {
      await pumpDetail(tester, null);
      expect(find.byKey(SessionDetailScreen.pcCopyKey), findsNothing);
    });
  });
}
