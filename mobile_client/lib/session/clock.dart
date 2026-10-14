/// Monotonic time source for session timing.
///
/// Injected so tests can control time precisely. Values are only meaningful
/// relative to each other (differences), never as wall-clock time.
abstract interface class Clock {
  /// Monotonic elapsed time since an arbitrary fixed origin.
  Duration now();
}

/// Production [Clock] backed by a [Stopwatch], which is monotonic and is not
/// affected by wall-clock changes (NTP sync, manual time changes).
class StopwatchClock implements Clock {
  StopwatchClock() : _stopwatch = Stopwatch()..start();

  final Stopwatch _stopwatch;

  @override
  Duration now() => _stopwatch.elapsed;
}
