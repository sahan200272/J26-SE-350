import 'package:flutter/material.dart';

import 'permissions/microphone_permission.dart';
import 'ui/recording_screen.dart';

void main() {
  runApp(const EchoVaultApp());
}

class EchoVaultApp extends StatelessWidget {
  const EchoVaultApp({
    super.key,
    this.permission = const MethodChannelMicrophonePermission(),
  });

  final MicrophonePermission permission;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Echo Vault',
      theme: ThemeData(colorScheme: .fromSeed(seedColor: Colors.indigo)),
      home: RecordingScreen(permission: permission),
    );
  }
}
