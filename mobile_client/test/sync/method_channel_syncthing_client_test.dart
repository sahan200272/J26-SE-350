import 'package:echo_vault/platform/app_channel.dart';
import 'package:echo_vault/sync/syncthing_client.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_syncthing_client.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final calls = <MethodCall>[];
  const client = MethodChannelSyncthingClient();

  void answer(Object? Function(MethodCall call) reply) =>
      messenger.setMockMethodCallHandler(appChannel, (call) async {
        calls.add(call);
        return reply(call);
      });

  setUp(calls.clear);
  tearDown(() => messenger.setMockMethodCallHandler(appChannel, null));

  final statusMap = {'running': true, 'version': 'v2.1.6', 'deviceId': 'ID'};

  test(
    'start and status use their channel methods and parse the map',
    () async {
      answer((_) => statusMap);
      final started = await client.start();
      final status = await client.status();
      expect(calls.map((c) => c.method), ['syncthingStart', 'syncthingStatus']);
      expect(started.running, isTrue);
      expect(status.version, 'v2.1.6');
      expect(status.deviceId, 'ID');
    },
  );

  test('setPeer sends the device ID and address', () async {
    answer((_) => {...statusMap, 'pcDeviceId': pcId});
    final s = await client.setPeer(
      deviceId: pcId,
      address: 'tcp://192.168.1.20:22000',
    );
    expect(calls.single.method, 'syncthingSetPeer');
    expect(calls.single.arguments, {
      'deviceId': pcId,
      'address': 'tcp://192.168.1.20:22000',
    });
    expect(s.pcDeviceId, pcId);
  });

  test('setPeer passes on BAD_PEER errors', () async {
    messenger.setMockMethodCallHandler(appChannel, (call) async {
      throw PlatformException(code: 'BAD_PEER', message: 'Invalid device ID');
    });
    expect(
      () => client.setPeer(deviceId: 'x', address: 'tcp://10.0.0.1:22000'),
      throwsA(
        isA<PlatformException>().having((e) => e.code, 'code', 'BAD_PEER'),
      ),
    );
  });

  test(
    'scan sends the outbox-relative path; qrPng returns the bytes',
    () async {
      final png = Uint8List.fromList([0x89, 0x50, 0x4e, 0x47]);
      answer((call) => call.method == 'syncthingScan' ? true : png);
      expect(await client.scan('20261018T100000_a1b2/x_00000.opus'), isTrue);
      expect(await client.qrPng(), png);
      expect(calls.first.method, 'syncthingScan');
      expect(calls.first.arguments, {
        'sub': '20261018T100000_a1b2/x_00000.opus',
      });
      expect(calls.last.method, 'syncthingQr');
    },
  );

  test('null replies throw (status) or count as not scanned (scan)', () async {
    answer((_) => null);
    expect(client.status, throwsA(isA<PlatformException>()));
    expect(client.qrPng, throwsA(isA<PlatformException>()));
    expect(await client.scan('x'), isFalse);
  });

  group('scanOnPublish', () {
    test(
      'scans <session_id>/<file> for each published file, in order',
      () async {
        final fake = FakeSyncthingClient();
        final onPublished = scanOnPublish(fake, '20261018T100000_a1b2');
        onPublished('20261018T100000_a1b2_00000.opus');
        onPublished('20261018T100000_a1b2_00000.json');
        onPublished('20261018T100000_a1b2_manifest.json');
        await pumpEventQueue();
        expect(fake.calls, [
          'scan:20261018T100000_a1b2/20261018T100000_a1b2_00000.opus',
          'scan:20261018T100000_a1b2/20261018T100000_a1b2_00000.json',
          'scan:20261018T100000_a1b2/20261018T100000_a1b2_manifest.json',
        ]);
      },
    );

    test('failures and a stopped Syncthing are logged, never thrown', () async {
      final log = <String>[];
      final fake = FakeSyncthingClient()..scanError = Exception('boom');
      scanOnPublish(fake, 's', log: log.add)('a.opus');
      await pumpEventQueue();
      fake
        ..scanError = null
        ..scanResult = false;
      scanOnPublish(fake, 's', log: log.add)('b.opus');
      await pumpEventQueue();
      expect(log, [
        '[sync] s/a.opus: scan failed: Exception: boom',
        '[sync] s/b.opus: Syncthing not running, scan skipped',
      ]);
    });
  });
}
