import 'dart:typed_data';

import 'package:echo_vault/encoding/method_channel_opus_encoder.dart';
import 'package:echo_vault/encoding/opus_encoder.dart';
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

  final reply = {
    'encoder': 'c2.android.opus.encoder',
    'bitrate': 32000,
    'inputSamples': 3,
    'packets': 1,
    'outputBytes': 321,
  };

  test('sends PCM16LE, 16 kHz mono, the bitrate and the output path', () async {
    answer((_) => reply);
    final result = await const MethodChannelOpusEncoder().encode(
      Int16List.fromList([1, -2, 32767]),
      '/files/staging/x_00000.opus',
    );
    final args = calls.single.arguments as Map;
    expect(calls.single.method, 'encodeOpus');
    expect(args['pcm'], Uint8List.fromList([1, 0, 0xfe, 0xff, 0xff, 0x7f]));
    expect(args['sampleRate'], 16000);
    expect(args['channels'], 1);
    expect(args['bitrate'], kDefaultOpusBitrate);
    expect(args['bitrate'], 32000);
    expect(args['outputPath'], '/files/staging/x_00000.opus');
    expect(result.encoderName, 'c2.android.opus.encoder');
    expect(result.bitrate, 32000);
    expect(result.packets, 1);
    expect(result.outputBytes, 321);
  });

  test('the bitrate is configurable', () async {
    answer((_) => {...reply, 'bitrate': 24000});
    final r = await const MethodChannelOpusEncoder(bitrate: 24000)
        .encode(Int16List(10), '/x.opus');
    expect((calls.single.arguments as Map)['bitrate'], 24000);
    expect(r.bitrate, 24000);
  });

  test('platform errors and empty replies throw', () async {
    messenger.setMockMethodCallHandler(appChannel, (call) async {
      throw PlatformException(code: 'ENCODE_FAILED', message: 'no codec');
    });
    await expectLater(
      const MethodChannelOpusEncoder().encode(Int16List(1), '/x.opus'),
      throwsA(isA<PlatformException>()),
    );
    answer((_) => null);
    await expectLater(
      const MethodChannelOpusEncoder().encode(Int16List(1), '/x.opus'),
      throwsA(isA<PlatformException>()),
    );
  });
}
