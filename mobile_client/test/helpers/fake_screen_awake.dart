import 'package:echo_vault/platform/app_channel.dart';

/// Records every setKeepScreenOn call.
class FakeScreenAwake implements ScreenAwake {
  final List<bool> calls = [];

  bool get isOn => calls.isNotEmpty && calls.last;

  @override
  Future<void> setKeepScreenOn(bool on) async => calls.add(on);
}
