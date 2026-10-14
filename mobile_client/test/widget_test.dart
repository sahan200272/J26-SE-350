import 'package:echo_vault/main.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers/fake_microphone_permission.dart';

void main() {
  testWidgets('app starts on the recording screen, idle', (tester) async {
    await tester.pumpWidget(
      EchoVaultApp(permission: FakeMicrophonePermission()),
    );
    expect(find.text('Echo Vault'), findsOneWidget);
    expect(find.text('Ready to record'), findsOneWidget);
    expect(find.text('Recording'), findsNothing);
  });
}
