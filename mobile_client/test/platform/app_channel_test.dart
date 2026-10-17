import 'package:echo_vault/platform/app_channel.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final calls = <MethodCall>[];

  void answer(Object? Function(MethodCall call) reply) =>
      messenger.setMockMethodCallHandler(appChannel, (call) async {
        calls.add(call);
        return reply(call);
      });

  setUp(calls.clear);
  tearDown(() => messenger.setMockMethodCallHandler(appChannel, null));

  test('one channel, unchanged name from A1', () {
    expect(appChannel.name, 'lk.sliit.j26se350.echo_vault/permissions');
  });

  test('setKeepScreenOn sends a bool', () async {
    answer((_) => null);
    const screen = MethodChannelScreenAwake();
    await screen.setKeepScreenOn(true);
    await screen.setKeepScreenOn(false);
    expect(calls.map((c) => (c.method, c.arguments)), [
      ('setKeepScreenOn', true),
      ('setKeepScreenOn', false),
    ]);
  });

  test('getFilesDir returns the path; empty is an error', () async {
    answer((_) => '/data/user/0/lk.sliit.j26se350.echo_vault/files');
    expect(
      await appFilesDir(),
      '/data/user/0/lk.sliit.j26se350.echo_vault/files',
    );
    answer((_) => null);
    await expectLater(appFilesDir(), throwsA(isA<PlatformException>()));
  });

  test('listOpusEncoders decodes the native list of maps', () async {
    answer(
      (_) => [
        {
          'name': 'c2.android.opus.encoder',
          'type': 'audio/opus',
          'sampleRates': [8000, 12000, 16000, 24000, 48000],
          'maxInputChannelCount': 2,
          'bitrateRange': [6000, 510000],
        },
      ],
    );
    final encoders = await listOpusEncoders();
    expect(calls.single.method, 'listOpusEncoders');
    expect(encoders.single['name'], 'c2.android.opus.encoder');
    expect(encoders.single['sampleRates'], contains(16000));

    answer((_) => null);
    expect(await listOpusEncoders(), isEmpty);
  });
}
