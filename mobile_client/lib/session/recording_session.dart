import 'dart:math';

import 'clock.dart';
import 'session_id.dart';

/// Lifecycle states of a single recording session.
///
/// `idle → recording ⇄ paused → stopped`. [stopped] is terminal; a new
/// recording needs a new [RecordingSession].
enum SessionState { idle, recording, paused, stopped }

/// User actions that drive a [RecordingSession].
enum SessionEvent { start, pause, resume, stop }

/// Why a pause began. [wireName] is the value written to the session
/// manifest.
enum PauseReason {
  /// The user pressed Pause.
  user('user'),

  /// The app left the foreground while recording (e.g. Home, screen lock,
  /// incoming-call screen).
  autoBackground('auto_background');

  const PauseReason(this.wireName);

  final String wireName;
}

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
  const PauseInterval(this.start, [this.end, this.reason = PauseReason.user]);

  final Duration start;
  final Duration? end;
  final PauseReason reason;

  bool get isOpen => end == null;

  @override
  bool operator ==(Object other) =>
      other is PauseInterval &&
      other.start == start &&
      other.end == end &&
      other.reason == reason;

  @override
  int get hashCode => Object.hash(start, end, reason);

  @override
  String toString() =>
      'PauseInterval($start, ${end ?? 'open'}, ${reason.wireName})';
}

/// One recording run: from Start or a Resume to the next Pause or Stop.
class RecordingRun {
  const RecordingRun(
    this.startOffset, {
    this.captureStartDelay,
    this.captureStartOffset,
  });

  /// Offset from session start at which the run began (the Start or Resume
  /// tap).
  final Duration startOffset;

  /// Monotonic time from the capture start/resume call to the first PCM
  /// bytes of this run; null until measured, or if none arrived.
  final Duration? captureStartDelay;

  /// Offset from session start at which capture actually began: arrival of
  /// the run's first PCM chunk minus that chunk's duration. Frame session
  /// offsets in this run count from here. Null until the first chunk.
  final Duration? captureStartOffset;

  @override
  bool operator ==(Object other) =>
      other is RecordingRun &&
      other.startOffset == startOffset &&
      other.captureStartDelay == captureStartDelay &&
      other.captureStartOffset == captureStartOffset;

  @override
  int get hashCode =>
      Object.hash(startOffset, captureStartDelay, captureStartOffset);

  @override
  String toString() =>
      'RecordingRun(tap $startOffset, delay ${captureStartDelay ?? 'none'}, '
      'capture start ${captureStartOffset ?? 'none'})';
}

/// Session state machine with recorded-time tracking (FR1, FR2).
///
/// Pure Dart: no Flutter imports, so it can be unit-tested and reused offline.
/// Recorded time excludes every pause; pause intervals are kept for the
/// session manifest (NFR7). Timing uses the monotonic [Clock]; the wall clock
/// is read once, at start, for [startWallClock] and [id].
class RecordingSession {
  RecordingSession({
    Clock? clock,
    DateTime Function()? wallClock,
    Random? random,
  }) : _clock = clock ?? StopwatchClock(),
       _wallClock = wallClock ?? DateTime.now,
       _random = random ?? Random.secure();

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
  final DateTime Function() _wallClock;
  final Random _random;
  SessionState _state = SessionState.idle;

  /// Clock reading at start; null until started.
  Duration? _startedAt;

  /// Clock reading at stop; null until stopped.
  Duration? _stoppedAt;

  DateTime? _startWallClock;
  String? _id;

  final List<RecordingRun> _runs = [];
  final List<PauseInterval> _pauses = [];

  SessionState get state => _state;

  /// `YYYYMMDDTHHMMSS_xxxx` from the local start time; null until started.
  String? get id => _id;

  /// Local wall-clock time at start (carries its UTC offset); null until
  /// started. Use [formatIso8601WithOffset] for the manifest form.
  DateTime? get startWallClock => _startWallClock;

  /// Recording runs so far, in order (for the session manifest).
  List<RecordingRun> get runs => List.unmodifiable(_runs);

  /// Recording runs begun so far: 1 after start, +1 per resume.
  int get runCount => _runs.length;

  /// Offset from session start at which the current recording run began:
  /// zero for the first run, the resume offset after a pause. Null unless
  /// recording.
  Duration? get runStartOffset =>
      _state == SessionState.recording ? _runs.last.startOffset : null;

  /// Records when capture of run [runIndex] (0-based) actually began, and
  /// the startup delay that led to it. Throws [RangeError] for a run that has
  /// not begun.
  void setCaptureStart(
    int runIndex, {
    required Duration delay,
    required Duration captureStartOffset,
  }) {
    RangeError.checkValidIndex(runIndex, _runs, 'runIndex');
    _runs[runIndex] = RecordingRun(
      _runs[runIndex].startOffset,
      captureStartDelay: delay,
      captureStartOffset: captureStartOffset,
    );
  }

  /// Converts a reading of this session's clock to an offset from session
  /// start. Only valid once started.
  Duration offsetAt(Duration clockReading) => clockReading - _startedAt!;

  /// Events accepted in the current state.
  List<SessionEvent> get allowedEvents => allowedEventsFor(_state);

  bool canHandle(SessionEvent event) =>
      _transitions[_state]!.containsKey(event);

  /// Pause intervals so far, as offsets from session start. The last one is
  /// open (no end) while the session is paused.
  List<PauseInterval> get pauseIntervals => List.unmodifiable(_pauses);

  /// Reason for the current pause; null unless paused.
  PauseReason? get pauseReason =>
      _state == SessionState.paused ? _pauses.last.reason : null;

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
  /// [pauseReason] is only used by [SessionEvent.pause].
  void handle(
    SessionEvent event, {
    PauseReason pauseReason = PauseReason.user,
  }) {
    final next = _transitions[_state]![event];
    if (next == null) throw InvalidTransitionError(_state, event);

    final now = _clock.now();
    switch (event) {
      case SessionEvent.start:
        _startedAt = now;
        final wall = _wallClock();
        _startWallClock = wall;
        _id = generateSessionId(wall, _random);
        _runs.add(const RecordingRun(Duration.zero));
      case SessionEvent.pause:
        _pauses.add(PauseInterval(now - _startedAt!, null, pauseReason));
      case SessionEvent.resume:
        _closeOpenPause(now);
        _runs.add(RecordingRun(now - _startedAt!));
      case SessionEvent.stop:
        _closeOpenPause(now);
        _stoppedAt = now;
    }
    _state = next;
  }

  void start() => handle(SessionEvent.start);
  void pause([PauseReason reason = PauseReason.user]) =>
      handle(SessionEvent.pause, pauseReason: reason);
  void resume() => handle(SessionEvent.resume);
  void stop() => handle(SessionEvent.stop);

  void _closeOpenPause(Duration now) {
    if (_pauses.isNotEmpty && _pauses.last.isOpen) {
      final open = _pauses.last;
      _pauses.last = PauseInterval(open.start, now - _startedAt!, open.reason);
    }
  }
}
