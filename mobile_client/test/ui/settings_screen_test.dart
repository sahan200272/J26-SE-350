import 'package:echo_vault/sync/syncthing_status.dart';
import 'package:echo_vault/ui/about_screen.dart';
import 'package:echo_vault/ui/settings_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_syncthing_client.dart';

final connection = find.byKey(SettingsScreen.connectionKey);
final pending = find.byKey(SettingsScreen.pendingKey);
final lanOnly = find.byKey(SettingsScreen.lanOnlyKey);
final deviceId = find.byKey(SettingsScreen.deviceIdKey);
final qr = find.byKey(SettingsScreen.qrKey);
final pcIdField = find.byKey(SettingsScreen.pcIdFieldKey);
final pcIpField = find.byKey(SettingsScreen.pcIpFieldKey);
final save = find.byKey(SettingsScreen.saveKey);
final saveMessage = find.byKey(SettingsScreen.saveMessageKey);

String textOf(WidgetTester tester, Finder f) {
  final widget = tester.widget(f);
  return switch (widget) {
    Text(:final data?) => data,
    SelectableText(:final data?) => data,
    _ => throw StateError('no text in $widget'),
  };
}

void main() {
  late FakeSyncthingClient syncthing;

  setUp(() => syncthing = FakeSyncthingClient());

  Future<void> pumpSettings(
    WidgetTester tester, {
    Duration poll = const Duration(seconds: 2),
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: SettingsScreen(syncthing: syncthing, pollInterval: poll),
      ),
    );
    await tester.pump(); // status
    await tester.pump(); // QR
  }

  Future<void> scrollTo(WidgetTester tester, Finder f) => tester
      .scrollUntilVisible(f, 200, scrollable: find.byType(Scrollable).first);

  testWidgets('shows this phone’s ID (text and QR), LAN-only check and no PC', (
    tester,
  ) async {
    await pumpSettings(tester);
    expect(textOf(tester, deviceId), phoneId);
    expect(qr, findsOneWidget);
    expect(syncthing.calls, containsAllInOrder(['status', 'qr']));
    expect(textOf(tester, connection), 'No PC set');
    expect(textOf(tester, lanOnly), 'LAN-only settings verified');
    expect(pending, findsNothing);
    expect(find.textContaining('tcp://0.0.0.0:22000'), findsOneWidget);
  });

  testWidgets('connected PC: "PC connected", pending chunks, fields filled', (
    tester,
  ) async {
    syncthing.current = runningStatus(
      pcDeviceId: pcId,
      pcAddress: 'tcp://192.168.1.20:22000',
      pcConnected: true,
      remoteState: 'valid',
      pendingChunks: 3,
    );
    await pumpSettings(tester);
    expect(textOf(tester, connection), 'PC connected');
    expect(find.text('192.168.1.20:22000 (tcp-client)'), findsOneWidget);
    expect(textOf(tester, pending), '3 chunks pending');
    await scrollTo(tester, save);
    expect(find.text(pcId), findsOneWidget);
    expect(find.text('192.168.1.20:22000'), findsWidgets);
  });

  testWidgets('status refreshes every poll interval', (tester) async {
    await pumpSettings(tester, poll: const Duration(seconds: 2));
    final before = syncthing.calls.where((c) => c == 'status').length;
    syncthing.current = runningStatus(
      pcDeviceId: pcId,
      pcAddress: 'tcp://192.168.1.20:22000',
      pcConnected: true,
      pendingChunks: 0,
    );
    await tester.pump(const Duration(seconds: 2));
    await tester.pump();
    expect(syncthing.calls.where((c) => c == 'status').length, before + 1);
    expect(textOf(tester, connection), 'PC connected');
    expect(textOf(tester, pending), '0 chunks pending');
  });

  testWidgets('invalid input shows errors and does not change the peer', (
    tester,
  ) async {
    await pumpSettings(tester);
    await scrollTo(tester, save);
    await tester.enterText(pcIdField, 'not-a-device-id');
    await tester.enterText(pcIpField, '8.8.8.8');
    await tester.tap(save);
    await tester.pump();
    expect(find.textContaining('characters; expected 56'), findsOneWidget);
    expect(find.textContaining('Not a LAN address'), findsOneWidget);
    expect(syncthing.calls.where((c) => c.startsWith('setPeer')), isEmpty);
  });

  testWidgets('valid input is normalised and saved as tcp://<ip>:22000', (
    tester,
  ) async {
    await pumpSettings(tester);
    await scrollTo(tester, save);
    await tester.enterText(pcIdField, pcId.replaceAll('-', '').toLowerCase());
    await tester.enterText(pcIpField, '192.168.1.20');
    await tester.pump();
    expect(find.text('Address: tcp://192.168.1.20:22000'), findsOneWidget);
    await tester.tap(save);
    await tester.pump();
    await tester.pump();
    expect(syncthing.calls, contains('setPeer:$pcId@tcp://192.168.1.20:22000'));
    expect(textOf(tester, saveMessage), contains('accept the device'));
    expect(find.text(pcId), findsOneWidget, reason: 'field shows canonical ID');
  });

  testWidgets('a rejected peer shows Syncthing’s message', (tester) async {
    syncthing.setPeerError = PlatformException(
      code: 'BAD_PEER',
      message: 'That is this phone\'s own device ID',
    );
    await pumpSettings(tester);
    await scrollTo(tester, save);
    await tester.enterText(pcIdField, phoneId);
    await tester.enterText(pcIpField, '10.0.0.2');
    await tester.tap(save);
    await tester.pump();
    await tester.pump();
    expect(textOf(tester, saveMessage), "That is this phone's own device ID");
  });

  testWidgets('Syncthing not running: error shown, Save disabled', (
    tester,
  ) async {
    syncthing.current = const SyncthingStatus(
      running: false,
      error: 'REST API did not answer within 60s',
      exitCode: 1,
    );
    await pumpSettings(tester);
    expect(textOf(tester, connection), 'Syncthing not running');
    expect(find.text('REST API did not answer within 60s'), findsOneWidget);
    expect(deviceId, findsNothing);
    await scrollTo(tester, save);
    expect(tester.widget<ButtonStyleButton>(save).onPressed, isNull);
  });

  testWidgets('three numbered steps; step 2 done once a PC is saved', (
    tester,
  ) async {
    await pumpSettings(tester);
    expect(find.text('Add this phone on your PC'), findsOneWidget);
    expect(find.text('Not connected to a PC yet'), findsOneWidget);
    await scrollTo(tester, save);
    expect(find.bySemanticsLabel('Step 2'), findsOneWidget);
    await tester.enterText(pcIdField, pcId);
    await tester.enterText(pcIpField, '192.168.1.20');
    await tester.tap(save);
    await tester.pump();
    await tester.pump();
    expect(find.bySemanticsLabel('Step 2, done'), findsOneWidget);
  });

  testWidgets('after a failed Save, errors update while typing', (
    tester,
  ) async {
    await pumpSettings(tester);
    await scrollTo(tester, save);
    await tester.enterText(pcIpField, '8.8.8.8');
    await tester.tap(save);
    await tester.pump();
    expect(find.textContaining('Not a LAN address'), findsOneWidget);

    await tester.enterText(pcIpField, '192.168.1.20');
    await tester.pump();
    expect(find.textContaining('Not a LAN address'), findsNothing);
    expect(syncthing.calls.where((c) => c.startsWith('setPeer')), isEmpty);
  });

  testWidgets('the info button opens About', (tester) async {
    await pumpSettings(tester);
    await tester.tap(find.byTooltip('About'));
    await tester.pumpAndSettle();
    expect(find.byType(AboutScreen), findsOneWidget);
  });
}
