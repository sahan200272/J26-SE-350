import 'dart:async';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/widgets.dart';

import '../capture/audio_capture.dart';
import '../capture/level_meter.dart';
import '../capture/pcm_framer.dart';
import '../capture/wav_writer.dart';
import '../permissions/microphone_permission.dart';
import '../platform/app_channel.dart';
import '../segmentation/segment.dart';
import '../segmentation/segmenter.dart';
import '../session/clock.dart';
import '../session/recording_session.dart';
import '../session/session_id.dart';
import '../vad/energy_vad.dart';
import 'lifecycle_source.dart';

/// Creates the sink that receives every frame of the session [sessionId].
typedef FrameSinkFactory = FrameSink Function(String sessionId);

/// Creates the function that receives every segment of the session
/// [sessionId] (debug builds: writes each segment as a WAV).
typedef SegmentSinkFactory = void Function(Segment segment) Function(
  String sessionId,
);

/// Creates the live segmenter of a session.
typedef SegmenterFactory = Segmenter Function(RecordingSession session);

/// Default live segmentation (A3): [VadSegmenter] with [EnergyVad], default
/// parameters.
Segmenter defaultSegmenter(RecordingSession session) => VadSegmenter.forSession(
  EnergyVad(),
  const VadSegmenterConfig(),
  sessionId: session.id,
  sessionStartWallClock: session.startWallClock,
);

/// Connects the recording screen to a [RecordingSession], the microphone
/// permission and the [AudioCapture]. Button availability is derived from
/// the session state machine.
///
/// Start is also offered after a session has stopped: it begins a *new*
/// session (the stopped one stays terminal).
///
/// FR2: Pause and Stop close the session's [PcmFramer] at once, so bytes that
/// still arrive are dropped and counted, never framed; capture itself is then
/// paused or stopped. Capture calls run one at a time and always catch up
/// with the latest session state.
///
/// Each run is anchored where capture actually began: the arrival of its
/// first chunk minus that chunk's duration. Every frame goes through the
/// session's [Segmenter] (FR3); Pause and Stop end the segmenter's run, so
/// segments never cross a pause.
class RecordingController extends ChangeNotifier {
  RecordingController({
    required this._permission,
    required this._capture,
    this._screenAwake = const MethodChannelScreenAwake(),
    LifecycleSource lifecycle = const AppLifecycleSource(),
    Clock? clock,
    this._wallClock,
    this._random,
    this.debugFrameSinkFactory,
    this.debugSegmentSinkFactory,
    this.segmenterFactory = defaultSegmenter,
    this.log,
    this.tickInterval = const Duration(milliseconds: 100),
  }) : _clock = clock ?? StopwatchClock() {
    _pcmSubscription = _capture.pcm.listen(_onPcm, onError: _onCaptureError);
    _stopLifecycle = lifecycle.listen(_onLifecycleChange);
  }

  final MicrophonePermission _permission;
  final AudioCapture _capture;
  final ScreenAwake _screenAwake;
  final Clock _clock;
  final DateTime Function()? _wallClock;
  final Random? _random;

  /// Debug builds only: e.g. a WAV writer per session.
  final FrameSinkFactory? debugFrameSinkFactory;

  /// Debug builds only: e.g. one WAV per segment.
  final SegmentSinkFactory? debugSegmentSinkFactory;

  final SegmenterFactory segmenterFactory;

  /// Debug log; null in release.
  final void Function(String message)? log;

  /// How often the elapsed timer and the input level are refreshed while
  /// recording.
  final Duration tickInterval;

  late final StreamSubscription<Uint8List> _pcmSubscription;
  late final VoidCallback _stopLifecycle;
  final _frames = StreamController<PcmFrame>.broadcast(sync: true);
  final _segments = StreamController<Segment>.broadcast(sync: true);

  _SessionRun? _current;
  bool _requestingPermission = false;
  String? _message;
  Timer? _ticker;
  bool _disposed = false;
  bool _keepScreenOn = false;

  final _level = RmsWindow();
  double? _levelDbfs;
  int _droppedOutsideSession = 0;

  // Capture state, driven by _reconcileCapture.
  _SessionRun? _captureOwner;
  bool _captureRunning = false;
  int _captureRun = 0;
  bool _reconciling = false;

  // Clock reading at the latest capture start/resume call (startup delay).
  Duration _captureCalledAt = Duration.zero;

  RecordingSession? get _session => _current?.session;

  SessionState get state => _session?.state ?? SessionState.idle;

  /// Recorded time excluding pauses.
  Duration get elapsed => _session?.recordedDuration ?? Duration.zero;

  /// Number of pauses in the current (or last) session.
  int get pauseCount => _session?.pauseIntervals.length ?? 0;

  List<PauseInterval> get pauseIntervals => _session?.pauseIntervals ?? [];

  /// Reason for the current pause; null unless paused.
  PauseReason? get pauseReason => _session?.pauseReason;

  String? get sessionId => _session?.id;

  /// Local wall-clock start of the current (or last) session.
  DateTime? get startWallClock => _session?.startWallClock;

  /// Recording runs of the current (or last) session, each with its capture
  /// startup delay once measured.
  List<RecordingRun> get runs => _session?.runs ?? [];

  /// Recording, but the current run's first PCM has not arrived yet: the UI
  /// shows "Starting microphone…" instead of the recording indicator.
  bool get isStartingCapture =>
      state == SessionState.recording &&
      _session!.runs.last.captureStartOffset == null;

  /// The segmenter is inside speech (onset seen, hangover not over).
  bool get isSpeechDetected =>
      state == SessionState.recording &&
      (_current?.segmenter.inSpeech ?? false);

  /// Segments emitted in the current (or last) session.
  int get segmentCount => _current?.segmenter.stats.segmentsEmitted ?? 0;

  /// The current (or last) session's segmenter, for its counters.
  Segmenter? get segmenter => _current?.segmenter;

  /// Every segment of every session, in order (sync broadcast).
  Stream<Segment> get segments => _segments.stream;

  /// RMS input level (dBFS) over the last refresh interval; null unless
  /// recording or before the first frame.
  double? get inputLevelDbfs =>
      state == SessionState.recording ? _levelDbfs : null;

  /// Every frame of every session, in order (sync broadcast).
  Stream<PcmFrame> get frames => _frames.stream;

  /// The current (or last) session's framer, for its counters. Read only.
  PcmFramer? get framer => _current?.framer;

  /// Bytes received while no session existed.
  int get droppedOutsideSession => _droppedOutsideSession;

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
        _beginSession();
      case MicPermissionStatus.denied:
        _message = deniedMessage;
      case MicPermissionStatus.permanentlyDenied:
        _message = permanentlyDeniedMessage;
    }
    notifyListeners();
  }

  void pause() => _pause(PauseReason.user);

  void resume() {
    if (!canResume) return;
    _session!.resume();
    _level.reset();
    _levelDbfs = null;
    _startTicker();
    log?.call(
      '[session] resumed at ${_session!.runStartOffset!.inMilliseconds} ms',
    );
    notifyListeners();
    _reconcileCapture();
  }

  void stop() {
    if (!canStop) return;
    _endSession(_current!);
    notifyListeners();
  }

  void _beginSession() {
    final session = RecordingSession(
      clock: _clock,
      wallClock: _wallClock,
      random: _random,
    )..start();
    final id = session.id!;
    _current = _SessionRun(
      session,
      PcmFramer(onDrop: _logDrop),
      debugFrameSinkFactory?.call(id),
      segmenterFactory(session),
      debugSegmentSinkFactory?.call(id),
    );
    _level.reset();
    _levelDbfs = null;
    _setKeepScreenOn(true);
    _startTicker();
    log?.call(
      '[session] $id started '
      '${formatIso8601WithOffset(session.startWallClock!)}',
    );
    _reconcileCapture();
  }

  void _pause(PauseReason reason) {
    if (!canPause) return;
    final run = _current!;
    run.session.pause(reason);
    _closeFramer(run);
    _logNoFirstChunk(run, 'pause');
    _stopTicker();
    log?.call(
      '[session] paused (${reason.wireName}) at '
      '${run.session.pauseIntervals.last.start.inMilliseconds} ms',
    );
    notifyListeners();
    _reconcileCapture();
  }

  void _endSession(_SessionRun run) {
    run.session.stop();
    _closeFramer(run);
    _logNoFirstChunk(run, 'stop');
    _stopTicker();
    _setKeepScreenOn(false);
    if (!run.captureStarted) _finish(run);
    _reconcileCapture();
  }

  void _onLifecycleChange(AppLifecycleState state) {
    switch (state) {
      // No longer visible: Home, Recents, screen lock, a full-screen
      // incoming-call UI. Not `inactive`, which also fires for the
      // notification shade and system dialogs while the app stays visible.
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
        if (canPause) {
          log?.call('[session] app ${state.name}: auto-pause');
          _pause(PauseReason.autoBackground);
        }
      case AppLifecycleState.resumed:
      case AppLifecycleState.inactive:
        // Resume is only ever a user action.
        break;
    }
  }

  void _onPcm(Uint8List bytes) {
    final run = _current;
    if (run == null) {
      _droppedOutsideSession += bytes.length;
      log?.call('[capture] dropped ${bytes.length} B: no session');
      return;
    }
    final framer = run.framer;
    if (framer.awaitingAnchor && bytes.isNotEmpty) {
      // First chunk of the run: it anchors the run's session offsets.
      final now = _clock.now();
      final clampedBefore = framer.clampedAnchors;
      final frames = framer.add(bytes, arrivedAt: run.session.offsetAt(now));
      _recordCaptureStart(
        run,
        now,
        bytes.length,
        clamped: framer.clampedAnchors > clampedBefore,
      );
      for (final frame in frames) {
        _deliver(run, frame);
      }
      notifyListeners(); // "Starting microphone…" → recording indicator
      return;
    }
    for (final frame in framer.add(bytes)) {
      _deliver(run, frame);
    }
  }

  void _recordCaptureStart(
    _SessionRun run,
    Duration now,
    int firstChunkBytes, {
    required bool clamped,
  }) {
    final index = run.framer.currentRun;
    final delay = now - _captureCalledAt;
    final start = run.framer.runStartOffset!;
    run.session.setCaptureStart(index, delay: delay, captureStartOffset: start);
    log?.call(
      '[capture] run $index startup delay ${_ms(delay)} ms '
      '(start/resume call → first $firstChunkBytes B); capture start '
      '${_ms(start)} ms (tap ${_ms(run.session.runs[index].startOffset)} ms)'
      '${clamped ? ', raised to the tap' : ''}',
    );
  }

  /// The run ended before any bytes arrived: it stays unanchored.
  void _logNoFirstChunk(_SessionRun run, String why) {
    final index = run.session.runCount - 1;
    if (run.session.runs[index].captureStartOffset != null) return;
    log?.call('[capture] run $index: no PCM before $why');
  }

  static String _ms(Duration d) => (d.inMicroseconds / 1000).toStringAsFixed(1);

  static String _describeRun(RecordingRun r) {
    final delay = r.captureStartDelay;
    final start = r.captureStartOffset;
    return 'tap ${_ms(r.startOffset)} ms / capture '
        '${start == null ? 'none' : '${_ms(start)} ms'} (startup '
        '${delay == null ? 'none' : '${_ms(delay)} ms'})';
  }

  /// Flushes the framer's partial frame, then ends the segmenter's run so
  /// that no segment crosses the pause or stop.
  void _closeFramer(_SessionRun run) {
    for (final frame in run.framer.close()) {
      _deliver(run, frame);
    }
    for (final segment in run.segmenter.endRun()) {
      _onSegment(run, segment);
    }
  }

  void _deliver(_SessionRun run, PcmFrame frame) {
    _level.add(frame.samples, frame.validSamples);
    run.sink?.add(frame);
    _frames.add(frame);
    final wasInSpeech = run.segmenter.inSpeech;
    final completed = run.segmenter.add(frame);
    for (final segment in completed) {
      _onSegment(run, segment);
    }
    // The speech indicator and segment count update at once, not only on
    // the next tick.
    if (completed.isNotEmpty || run.segmenter.inSpeech != wasInSpeech) {
      notifyListeners();
    }
  }

  void _onSegment(_SessionRun run, Segment segment) {
    log?.call(
      '[segment] #${segment.seq} run ${segment.run}: '
      '${_ms(segment.sessionStart)}–${_ms(segment.sessionEnd)} ms '
      '(audio samples ${segment.audioStartSample}–${segment.audioEndSample}), '
      'speech ratio ${segment.speechRatio.toStringAsFixed(2)}'
      '${segment.forcedSplit ? ', forced split' : ''}',
    );
    run.segmentSink?.call(segment);
    _segments.add(segment);
  }

  void _logDrop(int bytes, int total) => log?.call(
    '[capture] dropped $bytes B while ${state.name} (total $total B)',
  );

  void _onCaptureError(Object error) {
    final run = _current;
    if (run == null || run.session.state == SessionState.stopped) {
      log?.call('[capture] error with no active session: $error');
      return;
    }
    _onCaptureFailed(run, error);
  }

  void _onCaptureFailed(_SessionRun run, Object error) {
    log?.call('[capture] failed: $error');
    _captureRunning = false;
    if (run != _current || run.session.state == SessionState.stopped) return;
    _message = captureFailedMessage(error);
    _endSession(run);
    if (!_disposed) notifyListeners();
  }

  /// Brings the capture in line with the current session: start, pause,
  /// resume or stop, one call at a time. Re-entrant calls return at once; the
  /// running loop re-reads the state after every await.
  Future<void> _reconcileCapture() async {
    if (_reconciling) return;
    _reconciling = true;
    try {
      while (true) {
        final run = _current;
        final owner = _captureOwner;
        if (owner != null &&
            (owner != run || owner.session.state == SessionState.stopped)) {
          _captureOwner = null;
          _captureRunning = false;
          await _guard(owner, _capture.stop);
          _finish(owner);
          continue;
        }
        if (run == null) break;
        final session = run.session;
        final wantRunning = session.state == SessionState.recording;
        if (_captureRunning &&
            (!wantRunning || _captureRun != session.runCount)) {
          _captureRunning = false;
          await _guard(run, _capture.pause);
          continue;
        }
        if (wantRunning && !_captureRunning) {
          run.framer.openAtFirstChunk(
            run: session.runCount - 1,
            notBefore: session.runStartOffset!,
          );
          _captureRunning = true;
          _captureRun = session.runCount;
          _captureCalledAt = _clock.now();
          if (owner == run) {
            await _guard(run, _capture.resume);
          } else {
            _captureOwner = run;
            run.captureStarted = true;
            await _guard(run, _capture.start);
          }
          continue;
        }
        break;
      }
    } finally {
      _reconciling = false;
    }
  }

  Future<void> _guard(_SessionRun run, Future<void> Function() op) async {
    try {
      await op();
    } catch (e) {
      _onCaptureFailed(run, e);
    }
  }

  /// Capture for [run] has ended: close its sink and log a summary.
  void _finish(_SessionRun run) {
    if (run.finished) return;
    run.finished = true;
    final s = run.session;
    final f = run.framer;
    log?.call(
      '[session] ${s.id} finished: '
      'recorded=${s.recordedDuration.inMilliseconds} ms, '
      'total=${s.totalDuration.inMilliseconds} ms, '
      'pauses=${s.pauseIntervals}, '
      'frames=${f.framesEmitted} (padded ${f.paddedFrames}), '
      'framedSamples=${f.samplesFramed} '
      '(${samplesToDuration(f.samplesFramed).inMilliseconds} ms), '
      'acceptedBytes=${f.bytesAccepted}, '
      'droppedBytes=${f.droppedBytes} in ${f.droppedChunks} chunks, '
      'oddBytesDiscarded=${f.discardedOddBytes}, '
      'runs=[${s.runs.map(_describeRun).join(', ')}], '
      'segmenter=${run.segmenter.stats.toJson()}',
    );
    final sink = run.sink;
    if (sink != null) unawaited(sink.close());
  }

  void _setKeepScreenOn(bool on) {
    if (_keepScreenOn == on) return;
    _keepScreenOn = on;
    _screenAwake.setKeepScreenOn(on).catchError((Object e) {
      log?.call('[screen] setKeepScreenOn($on) failed: $e');
    });
  }

  void _startTicker() {
    _ticker?.cancel();
    _ticker = Timer.periodic(tickInterval, (_) {
      _levelDbfs = _level.takeDbfs() ?? _levelDbfs;
      notifyListeners();
    });
  }

  void _stopTicker() {
    _ticker?.cancel();
    _ticker = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _stopTicker();
    _stopLifecycle();
    if (_current case final run?
        when run.session.canHandle(SessionEvent.stop)) {
      _endSession(run);
    }
    _setKeepScreenOn(false);
    unawaited(_pcmSubscription.cancel());
    unawaited(_frames.close());
    unawaited(_segments.close());
    super.dispose();
  }

  static const deniedMessage =
      'Microphone permission was denied. Echo Vault needs the microphone to '
      'record. Tap Start to ask again.';
  static const permanentlyDeniedMessage =
      'Microphone access is blocked. Allow it in Settings › Apps › Echo Vault '
      '› Permissions, then tap Start.';

  static String captureFailedMessage(Object error) {
    final detail = error is CaptureFailure ? error.message : '$error';
    return 'Recording stopped: the microphone failed ($detail).';
  }
}

/// Everything that belongs to one session while it runs.
class _SessionRun {
  _SessionRun(
    this.session,
    this.framer,
    this.sink,
    this.segmenter,
    this.segmentSink,
  );

  final RecordingSession session;
  final PcmFramer framer;
  final FrameSink? sink;
  final Segmenter segmenter;
  final void Function(Segment segment)? segmentSink;

  /// AudioCapture.start was issued for this session.
  bool captureStarted = false;

  /// Sink closed and summary logged.
  bool finished = false;
}
