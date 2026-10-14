import 'package:echo_vault/session/clock.dart';

/// Manually advanced [Clock] for deterministic timing tests.
class FakeClock implements Clock {
  Duration _now = Duration.zero;

  @override
  Duration now() => _now;

  void advance(Duration d) => _now += d;
}
