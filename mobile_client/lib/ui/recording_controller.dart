import 'dart:async';

import 'package:flutter/foundation.dart';

import '../permissions/microphone_permission.dart';
import '../session/clock.dart';
import '../session/recording_session.dart';

/// Connects the recording screen to a [RecordingSession] and the microphone
/// permission. Button availability is derived from the session state machine.
///
/// Start is also offered after a session has stopped: it begins a *new*
/// session (the stopped one stays terminal).
class RecordingController extends ChangeNotifier {
  RecordingController({
    required this._permission,
    Clock? clock,
    this.tickInterval = const Duration(milliseconds: 250),
  }) : _clock = clock ?? StopwatchClock();

  final MicrophonePermission _permission;
  final Clock _clock;

  /// How often the elapsed timer is refreshed while recording.
  final Duration tickInterval;

  RecordingSession? _session;
  bool _requestingPermission = false;
  String? _message;
  Timer? _ticker;
  bool _disposed = false;

  SessionState get state => _session?.state ?? SessionState.idle;

  /// Recorded time excluding pauses.
  Duration get elapsed => _session?.recordedDuration ?? Duration.zero;

  /// Number of pauses in the current (or last) session.
  int get pauseCount => _session?.pauseIntervals.length ?? 0;

  /// User-facing problem to show, e.g. a denied permission. Null when none.
  String? get message => _message;

  bool get isRequestingPermission => _requestingPermission;

  bool get canStart =>
      !_requestingPermission &&
      (state == SessionState.idle || state == SessionState.stopped);
  bool get canPause => _session?.canHandle(SessionEvent.pause) ?? false;
  bool get canResume => _session?.canHandle(SessionEvent.resume) ?? false;
  bool get canStop => _session?.canHandle(SessionEvent.stop) ?? false;

  /// Asks for microphone access, then starts a new session only if granted.
  Future<void> start() async {
    if (!canStart) return;
    _requestingPermission = true;
    _message = null;
    notifyListeners();

    MicPermissionStatus status;
    try {
      status = await _permission.request();
    } catch (_) {
      status = MicPermissionStatus.denied;
    }
    if (_disposed) return;
    _requestingPermission = false;

    switch (status) {
      case MicPermissionStatus.granted:
        _session = RecordingSession(clock: _clock)..start();
        _startTicker();
      case MicPermissionStatus.denied:
        _message = deniedMessage;
      case MicPermissionStatus.permanentlyDenied:
        _message = permanentlyDeniedMessage;
    }
    notifyListeners();
  }

  void pause() {
    if (!canPause) return;
    _session!.pause();
    _stopTicker();
    notifyListeners();
  }

  void resume() {
    if (!canResume) return;
    _session!.resume();
    _startTicker();
    notifyListeners();
  }

  void stop() {
    if (!canStop) return;
    _session!.stop();
    _stopTicker();
    notifyListeners();
  }

  void _startTicker() {
    _ticker?.cancel();
    _ticker = Timer.periodic(tickInterval, (_) => notifyListeners());
  }

  void _stopTicker() {
    _ticker?.cancel();
    _ticker = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _stopTicker();
    super.dispose();
  }

  static const deniedMessage =
      'Microphone permission was denied. Echo Vault needs the microphone to '
      'record. Tap Start to ask again.';
  static const permanentlyDeniedMessage =
      'Microphone access is blocked. Allow it in Settings › Apps › Echo Vault '
      '› Permissions, then tap Start.';
}
