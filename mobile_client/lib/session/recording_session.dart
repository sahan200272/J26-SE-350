import 'clock.dart';

/// Lifecycle states of a single recording session.
///
/// `idle → recording ⇄ paused → stopped`. [stopped] is terminal; a new
/// recording needs a new [RecordingSession].
enum SessionState { idle, recording, paused, stopped }

/// User actions that drive a [RecordingSession].
enum SessionEvent { start, pause, resume, stop }

/// Thrown when an event is not allowed in the session's current state.
///
/// The session state is left unchanged when this is thrown.
class InvalidTransitionError extends StateError {
  InvalidTransitionError(this.from, this.event)
    : super(
        'Cannot ${event.name} a session that is ${from.name}. '
        'Allowed in ${from.name}: ${_describeAllowed(from)}.',
      );

  final SessionState from;
  final SessionEvent event;

  static String _describeAllowed(SessionState state) {
    final allowed = RecordingSession.allowedEventsFor(state);
    return allowed.isEmpty ? 'none' : allowed.map((e) => e.name).join(', ');
  }
}

/// A pause within a session, as offsets from the session start on the
/// session's monotonic clock. [end] is null while the pause is still open.
class PauseInterval {
  const PauseInterval(this.start, [this.end]);

  final Duration start;
  final Duration? end;

  bool get isOpen => end == null;

  @override
  bool operator ==(Object other) =>
      other is PauseInterval && other.start == start && other.end == end;

  @override
  int get hashCode => Object.hash(start, end);

  @override
  String toString() => 'PauseInterval($start, ${end ?? 'open'})';
}

/// Session state machine with recorded-time tracking (FR1, FR2).
///
/// Pure Dart: no Flutter imports, so it can be unit-tested and reused offline.
/// Recorded time excludes every pause; pause intervals are kept for the
/// session manifest (NFR7).
class RecordingSession {
  RecordingSession({Clock? clock}) : _clock = clock ?? StopwatchClock();

  static const Map<SessionState, Map<SessionEvent, SessionState>> _transitions =
      {
        SessionState.idle: {SessionEvent.start: SessionState.recording},
        SessionState.recording: {
          SessionEvent.pause: SessionState.paused,
          SessionEvent.stop: SessionState.stopped,
        },
        SessionState.paused: {
          SessionEvent.resume: SessionState.recording,
          SessionEvent.stop: SessionState.stopped,
        },
        SessionState.stopped: {},
      };

  /// Events accepted in [state], in declaration order.
  static List<SessionEvent> allowedEventsFor(SessionState state) =>
      SessionEvent.values.where(_transitions[state]!.containsKey).toList();

  final Clock _clock;
  SessionState _state = SessionState.idle;

  /// Clock reading at start; null until started.
  Duration? _startedAt;

  /// Clock reading at stop; null until stopped.
  Duration? _stoppedAt;

  final List<PauseInterval> _pauses = [];

  SessionState get state => _state;

  /// Events accepted in the current state.
  List<SessionEvent> get allowedEvents => allowedEventsFor(_state);

  bool canHandle(SessionEvent event) =>
      _transitions[_state]!.containsKey(event);

  /// Pause intervals so far, as offsets from session start. The last one is
  /// open (no end) while the session is paused.
  List<PauseInterval> get pauseIntervals => List.unmodifiable(_pauses);

  /// Offset from session start to stop; null unless stopped.
  Duration? get stoppedOffset =>
      _stoppedAt == null ? null : _stoppedAt! - _startedAt!;

  /// Time since start, including pauses. Frozen once stopped.
  Duration get totalDuration {
    final start = _startedAt;
    if (start == null) return Duration.zero;
    return (_stoppedAt ?? _clock.now()) - start;
  }

  /// Total paused time, including an open pause up to now.
  Duration get pausedDuration {
    final total = totalDuration;
    return _pauses.fold(
      Duration.zero,
      (sum, p) => sum + ((p.end ?? total) - p.start),
    );
  }

  /// Time spent recording, excluding all pauses. Frozen while paused and
  /// once stopped.
  Duration get recordedDuration => totalDuration - pausedDuration;

  /// Applies [event]; throws [InvalidTransitionError] if not allowed.
  void handle(SessionEvent event) {
    final next = _transitions[_state]![event];
    if (next == null) throw InvalidTransitionError(_state, event);

    final now = _clock.now();
    switch (event) {
      case SessionEvent.start:
        _startedAt = now;
      case SessionEvent.pause:
        _pauses.add(PauseInterval(now - _startedAt!));
      case SessionEvent.resume:
        _closeOpenPause(now);
      case SessionEvent.stop:
        _closeOpenPause(now);
        _stoppedAt = now;
    }
    _state = next;
  }

  void start() => handle(SessionEvent.start);
  void pause() => handle(SessionEvent.pause);
  void resume() => handle(SessionEvent.resume);
  void stop() => handle(SessionEvent.stop);

  void _closeOpenPause(Duration now) {
    if (_pauses.isNotEmpty && _pauses.last.isOpen) {
      _pauses.last = PauseInterval(_pauses.last.start, now - _startedAt!);
    }
  }
}
