import 'package:echo_vault/main.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fake_audio_capture.dart';
import 'helpers/fake_microphone_permission.dart';
import 'helpers/fake_screen_awake.dart';

void main() {
  testWidgets('app starts on the recording screen, idle', (tester) async {
    final capture = FakeAudioCapture();
    await tester.pumpWidget(
      EchoVaultApp(
        permission: FakeMicrophonePermission(),
        capture: capture,
        screenAwake: FakeScreenAwake(),
      ),
    );
    expect(find.text('Echo Vault'), findsOneWidget);
    expect(find.text('Ready to record'), findsOneWidget);
    expect(find.text('Recording'), findsNothing);
    expect(capture.calls, isEmpty, reason: 'no capture before Start');
  });
}
