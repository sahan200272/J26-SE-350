import 'package:echo_vault/ui/app_shell.dart';
import 'package:echo_vault/ui/home_screen.dart';
import 'package:echo_vault/ui/mic_explainer_sheet.dart';
import 'package:echo_vault/ui/onboarding_screen.dart';
import 'package:echo_vault/ui/onboarding_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('welcome: optional Connect your PC page', () {
    Future<void> toLastPage(WidgetTester tester) async {
      for (var i = 0; i < 3; i++) {
        await tester.tap(find.byKey(OnboardingScreen.nextKey));
        await tester.pumpAndSettle();
      }
    }

    testWidgets('Connect my PC calls onConnectPc', (tester) async {
      var connect = 0;
      var done = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: OnboardingScreen(
            onDone: () => done++,
            onConnectPc: () => connect++,
          ),
        ),
      );
      await toLastPage(tester);
      expect(find.text('Connect your PC'), findsOneWidget);
      expect(find.text('Connect my PC'), findsOneWidget);

      await tester.tap(find.byKey(OnboardingScreen.nextKey));
      await tester.pump();
      expect(connect, 1);
      expect(done, 0);
    });

    testWidgets('Not now finishes the welcome without pairing', (
      tester,
    ) async {
      var connect = 0;
      var done = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: OnboardingScreen(
            onDone: () => done++,
            onConnectPc: () => connect++,
          ),
        ),
      );
      await toLastPage(tester);
      await tester.tap(find.byKey(OnboardingScreen.laterKey));
      await tester.pump();
      expect(done, 1);
      expect(connect, 0);
    });
  });

  group('microphone explainer (first tap only)', () {
    Widget shell(OnboardingStore store) => MaterialApp(
      home: AppShell(
        recordingBuilder: (_) => const Scaffold(body: Text('recorder')),
        micExplainerStore: store,
      ),
    );

    testWidgets('Not now stays on Home; Continue opens the recorder once', (
      tester,
    ) async {
      final store = MemoryOnboardingStore();
      await tester.pumpWidget(shell(store));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(HomeScreen.startKey));
      await tester.pumpAndSettle();
      expect(find.text(MicExplainerSheet.title), findsOneWidget);

      await tester.tap(find.byKey(MicExplainerSheet.notNowKey));
      await tester.pumpAndSettle();
      expect(find.text('recorder'), findsNothing);
      expect(store.complete, isFalse, reason: 'shown again next time');

      await tester.tap(find.byKey(HomeScreen.startKey));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(MicExplainerSheet.continueKey));
      await tester.pumpAndSettle();
      expect(find.text('recorder'), findsOneWidget);
      expect(store.complete, isTrue);

      tester.state<NavigatorState>(find.byType(Navigator)).pop();
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(HomeScreen.startKey));
      await tester.pumpAndSettle();
      expect(find.text(MicExplainerSheet.title), findsNothing);
      expect(find.text('recorder'), findsOneWidget);
    });

    testWidgets('already explained: the recorder opens directly', (
      tester,
    ) async {
      await tester.pumpWidget(shell(MemoryOnboardingStore(complete: true)));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(HomeScreen.startKey));
      await tester.pumpAndSettle();
      expect(find.text(MicExplainerSheet.title), findsNothing);
      expect(find.text('recorder'), findsOneWidget);
    });
  });
}
