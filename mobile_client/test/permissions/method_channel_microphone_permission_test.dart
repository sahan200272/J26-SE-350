import 'package:echo_vault/permissions/microphone_permission.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const permission = MethodChannelMicrophonePermission();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  void answer(Object? reply) => messenger.setMockMethodCallHandler(
    MethodChannelMicrophonePermission.channel,
    (call) async {
      expect(call.method, 'requestMicrophone');
      return reply;
    },
  );

  tearDown(
    () => messenger.setMockMethodCallHandler(
      MethodChannelMicrophonePermission.channel,
      null,
    ),
  );

  test('maps native replies to statuses', () async {
    answer('granted');
    expect(await permission.request(), MicPermissionStatus.granted);
    answer('denied');
    expect(await permission.request(), MicPermissionStatus.denied);
    answer('permanentlyDenied');
    expect(await permission.request(), MicPermissionStatus.permanentlyDenied);
  });

  test('unknown or null reply is treated as denied', () async {
    answer('somethingElse');
    expect(await permission.request(), MicPermissionStatus.denied);
    answer(null);
    expect(await permission.request(), MicPermissionStatus.denied);
  });
}
