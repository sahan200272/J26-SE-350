import 'package:echo_vault/ui/lifecycle_source.dart';
import 'package:flutter/widgets.dart';

/// [LifecycleSource] driven by the test with [emit].
class FakeLifecycle implements LifecycleSource {
  ValueChanged<AppLifecycleState>? _listener;

  bool get isListening => _listener != null;

  void emit(AppLifecycleState state) => _listener?.call(state);

  @override
  VoidCallback listen(ValueChanged<AppLifecycleState> onChange) {
    _listener = onChange;
    return () => _listener = null;
  }
}
