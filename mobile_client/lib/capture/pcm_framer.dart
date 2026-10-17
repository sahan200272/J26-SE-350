import 'dart:typed_data';

import 'audio_capture.dart';

/// Samples per frame: 512 at 16 kHz = 32 ms (the Silero VAD v5 frame size).
const int kFrameSamples = 512;

/// Converts a sample count at [sampleRate] to a [Duration] (µs, truncated).
Duration samplesToDuration(int samples, [int sampleRate = kSampleRate]) =>
    Duration(
      microseconds: samples * Duration.microsecondsPerSecond ~/ sampleRate,
    );

/// A fixed-size block of 16-bit mono samples.
///
/// Every frame lies inside one recording run (never across a pause). The last
/// frame of a run can be partial: its first [validSamples] samples are real
/// and the rest of [samples] is zero padding.
class PcmFrame {
  const PcmFrame({
    required this.index,
    required this.run,
    required this.samples,
    required this.validSamples,
    required this.audioOffsetSamples,
    required this.sessionOffset,
    this.sampleRate = kSampleRate,
  });

  /// 0-based position in the session.
  final int index;

  /// 0-based recording run (0 until the first pause, +1 per resume); the
  /// index into `RecordingSession.runs` when set by the controller.
  final int run;

  /// Always the framer's frame size long.
  final Int16List samples;
  final int validSamples;

  /// Real samples before this frame on the audio timeline (pauses excluded).
  /// Exact; [audioOffset] is the same value as a [Duration].
  final int audioOffsetSamples;

  /// Start of this frame on the session timeline (pauses included): the
  /// run's start offset plus the samples captured since that run began.
  final Duration sessionOffset;

  final int sampleRate;

  Duration get audioOffset => samplesToDuration(audioOffsetSamples, sampleRate);

  /// Duration of the real samples.
  Duration get duration => samplesToDuration(validSamples, sampleRate);

  bool get isPadded => validSamples < samples.length;
}

/// Turns arbitrary PCM16LE byte chunks into fixed [frameSamples] frames,
/// with no samples lost or duplicated (FR2, NFR7).
///
/// The framer is open only during a recording run ([open] … [close]). Bytes
/// passed to [add] while it is closed (paused or stopped) are dropped and
/// counted, never framed. A chunk may end in the middle of a sample; the odd
/// byte is kept for the next chunk of the same run.
///
/// Pure Dart: no Flutter imports.
class PcmFramer {
  PcmFramer({
    this.frameSamples = kFrameSamples,
    this.sampleRate = kSampleRate,
    this.onDrop,
  }) : assert(frameSamples > 0),
       _buffer = Int16List(frameSamples);

  final int frameSamples;
  final int sampleRate;

  /// Called with the size of each dropped chunk (for debug logging).
  final void Function(int droppedBytes, int totalDroppedBytes)? onDrop;

  Int16List _buffer;
  int _fill = 0;
  int? _pendingLowByte;

  bool _open = false;
  int _run = -1;
  int _runsOpened = 0;
  Duration _runStart = Duration.zero;
  bool _awaitingAnchor = false;
  Duration _notBefore = Duration.zero;
  int _clampedAnchors = 0;
  int _samplesInRun = 0;

  int _framesEmitted = 0;
  int _paddedFrames = 0;
  int _samplesFramed = 0;
  int _bytesAccepted = 0;
  int _droppedBytes = 0;
  int _droppedChunks = 0;
  int _discardedOddBytes = 0;

  bool get isOpen => _open;

  /// Runs opened so far.
  int get runCount => _runsOpened;
  int get framesEmitted => _framesEmitted;

  /// Partial (zero-padded) frames emitted by [close].
  int get paddedFrames => _paddedFrames;

  /// Real samples emitted in frames (padding excluded).
  int get samplesFramed => _samplesFramed;

  /// Bytes received while open.
  int get bytesAccepted => _bytesAccepted;

  /// Bytes received while closed (paused, stopped or not yet started).
  int get droppedBytes => _droppedBytes;
  int get droppedChunks => _droppedChunks;

  /// Half-samples left over when a run closed (a run that ended on an odd
  /// byte count). Normally 0.
  int get discardedOddBytes => _discardedOddBytes;

  /// The current (or last) run's index; -1 before the first [open].
  int get currentRun => _run;

  /// Session offset of the current (or last) run's first sample; null while
  /// a run opened with [openAtFirstChunk] still waits for its first chunk.
  Duration? get runStartOffset => _awaitingAnchor ? null : _runStart;

  /// The open run is waiting for its first chunk to set its start offset.
  bool get awaitingAnchor => _awaitingAnchor;

  /// Runs whose computed start was earlier than allowed and was raised to
  /// `notBefore` (see [openAtFirstChunk]). Normally 0.
  int get clampedAnchors => _clampedAnchors;

  /// Starts a recording run whose first sample is at [sessionOffset] on the
  /// session timeline. [run] is the session's run index for [PcmFrame.run]
  /// (default: previous + 1); it must increase, because a run that never
  /// received capture (paused before it started) is skipped.
  void open(Duration sessionOffset, {int? run}) {
    _openRun(run);
    _runStart = sessionOffset;
  }

  /// Starts a recording run whose start is only known when its first chunk
  /// arrives: [add] then needs `arrivedAt` (the session offset at which the
  /// chunk arrived), and the run starts at `arrivedAt` minus that chunk's
  /// duration, the moment its first sample was captured. The start is never
  /// earlier than [notBefore] (the Start/Resume tap): an earlier value would
  /// put the run inside the preceding pause.
  void openAtFirstChunk({int? run, Duration notBefore = Duration.zero}) {
    _openRun(run);
    _awaitingAnchor = true;
    _notBefore = notBefore;
  }

  void _openRun(int? run) {
    if (_open) throw StateError('PcmFramer is already open.');
    final next = run ?? _run + 1;
    if (next <= _run) {
      throw ArgumentError.value(run, 'run', 'must be greater than $_run');
    }
    _open = true;
    _run = next;
    _runsOpened++;
    _samplesInRun = 0;
    _awaitingAnchor = false;
  }

  /// Frames [bytes]. Returns the frames completed by this chunk (often none).
  /// While closed, [bytes] are dropped and counted. [arrivedAt] is required
  /// for the first non-empty chunk of a run opened with [openAtFirstChunk].
  List<PcmFrame> add(Uint8List bytes, {Duration? arrivedAt}) {
    if (!_open) {
      _droppedBytes += bytes.length;
      _droppedChunks++;
      onDrop?.call(bytes.length, _droppedBytes);
      return const [];
    }
    if (_awaitingAnchor && bytes.isNotEmpty) {
      if (arrivedAt == null) {
        throw ArgumentError.notNull('arrivedAt');
      }
      final start =
          arrivedAt - samplesToDuration(bytes.length ~/ 2, sampleRate);
      if (start < _notBefore) _clampedAnchors++;
      _runStart = start < _notBefore ? _notBefore : start;
      _awaitingAnchor = false;
    }
    _bytesAccepted += bytes.length;

    final frames = <PcmFrame>[];
    final n = bytes.length;
    var i = 0;
    if (_pendingLowByte case final low? when n > 0) {
      _push(low | (bytes[0] << 8), frames);
      _pendingLowByte = null;
      i = 1;
    }
    for (; i + 1 < n; i += 2) {
      _push(bytes[i] | (bytes[i + 1] << 8), frames);
    }
    if (i < n) _pendingLowByte = bytes[i];
    return frames;
  }

  /// Ends the current run. Emits the remaining samples as one zero-padded
  /// frame (if any) so that no frame spans a pause. A dangling half-sample is
  /// discarded and counted in [discardedOddBytes]. No-op when closed.
  List<PcmFrame> close() {
    if (!_open) return const [];
    _open = false;
    _awaitingAnchor = false;
    if (_pendingLowByte != null) {
      _pendingLowByte = null;
      _discardedOddBytes++;
    }
    if (_fill == 0) return const [];
    _paddedFrames++;
    return [_emit(_fill)];
  }

  void _push(int sample, List<PcmFrame> out) {
    // Int16List stores the low 16 bits, so 0x8000..0xFFFF become negative.
    _buffer[_fill++] = sample;
    if (_fill == frameSamples) out.add(_emit(frameSamples));
  }

  PcmFrame _emit(int valid) {
    final frame = PcmFrame(
      index: _framesEmitted,
      run: _run,
      samples: _buffer,
      validSamples: valid,
      audioOffsetSamples: _samplesFramed,
      sessionOffset: _runStart + samplesToDuration(_samplesInRun, sampleRate),
      sampleRate: sampleRate,
    );
    _framesEmitted++;
    _samplesFramed += valid;
    _samplesInRun += valid;
    _buffer = Int16List(frameSamples);
    _fill = 0;
    return frame;
  }
}
