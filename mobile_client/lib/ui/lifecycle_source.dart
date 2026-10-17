import 'package:flutter/widgets.dart';

/// Source of app lifecycle changes. Abstracted so the controller's auto-pause
/// can be tested without a binding.
abstract interface class LifecycleSource {
  /// Delivers every lifecycle change to [onChange] until the returned
  /// function is called.
  VoidCallback listen(ValueChanged<AppLifecycleState> onChange);
}

/// Production source: an [AppLifecycleListener] on the widgets binding.
class AppLifecycleSource implements LifecycleSource {
  const AppLifecycleSource();

  @override
  VoidCallback listen(ValueChanged<AppLifecycleState> onChange) =>
      AppLifecycleListener(onStateChange: onChange).dispose;
}
