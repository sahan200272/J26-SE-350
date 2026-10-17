part of 'segmenter.dart';

/// Parameters of [VadSegmenter]. Frame counts are 32 ms frames.
class VadSegmenterConfig {
  const VadSegmenterConfig({
    this.onsetFrames = 3,
    this.hangoverFrames = 19,
    this.preRollFrames = 10,
    this.postRollFrames = 8,
    this.minSpeechMs = 200,
    this.maxSegmentMs = 30000,
  }) : assert(onsetFrames >= 1),
       assert(hangoverFrames >= 1),
       assert(preRollFrames >= 0),
       assert(postRollFrames >= 0 && postRollFrames <= hangoverFrames),
       assert(minSpeechMs >= 0),
       assert(maxSegmentMs >= 1000);

  /// A segment starts after this many consecutive speech frames.
  final int onsetFrames;

  /// ...and ends after this many consecutive non-speech frames (hangover).
  final int hangoverFrames;

  /// Frames before the onset that are included (soft word beginnings),
  /// limited to what the current run has.
  final int preRollFrames;

  /// Frames after the last speech frame that are included; at most
  /// [hangoverFrames], since only those have been seen when the segment
  /// ends.
  final int postRollFrames;

  /// Segments whose speech (onset to last speech frame) is shorter are
  /// discarded and counted (clicks, taps). Not applied to the continuation
  /// after a forced split.
  final int minSpeechMs;

  /// Longer segments are split (Whisper's 30 s window); no segment exceeds
  /// this, pre-roll included.
  final int maxSegmentMs;

  Map<String, Object?> toJson() => {
    'onset_frames': onsetFrames,
    'hangover_frames': hangoverFrames,
    'pre_roll_frames': preRollFrames,
    'post_roll_frames': postRollFrames,
    'min_speech_ms': minSpeechMs,
    'max_segment_ms': maxSegmentMs,
  };

  factory VadSegmenterConfig.fromJson(Map<String, Object?> json) =>
      VadSegmenterConfig(
        onsetFrames: json['onset_frames']! as int,
        hangoverFrames: json['hangover_frames']! as int,
        preRollFrames: json['pre_roll_frames']! as int,
        postRollFrames: json['post_roll_frames']! as int,
        minSpeechMs: json['min_speech_ms']! as int,
        maxSegmentMs: json['max_segment_ms']! as int,
      );

  @override
  bool operator ==(Object other) =>
      other is VadSegmenterConfig &&
      other.onsetFrames == onsetFrames &&
      other.hangoverFrames == hangoverFrames &&
      other.preRollFrames == preRollFrames &&
      other.postRollFrames == postRollFrames &&
      other.minSpeechMs == minSpeechMs &&
      other.maxSegmentMs == maxSegmentMs;

  @override
  int get hashCode => Object.hash(
    onsetFrames,
    hangoverFrames,
    preRollFrames,
    postRollFrames,
    minSpeechMs,
    maxSegmentMs,
  );

  @override
  String toString() => 'VadSegmenterConfig(${toJson()})';
}

/// Proposed-style segmentation with any [Vad]: onset after
/// [VadSegmenterConfig.onsetFrames] speech frames, offset after
/// [VadSegmenterConfig.hangoverFrames] non-speech frames, with pre-roll,
/// post-roll, a minimum speech length and a forced split at the maximum
/// length.
class VadSegmenter extends _SegmenterBase {
  VadSegmenter(super.vad, [this.settings = const VadSegmenterConfig()])
    : super();

  VadSegmenter.forSession(
    super.vad,
    this.settings, {
    super.sessionId,
    super.sessionStartWallClock,
  });

  final VadSegmenterConfig settings;

  // Idle: frames that may still become pre-roll or onset.
  final _pending = <_Frame>[];
  int _speechRun = 0;

  // In speech: the open segment.
  List<_Frame>? _segment;
  int _segmentSamples = 0;
  int _silenceRun = 0;
  int _onsetIndex = 0;
  bool _continuation = false;

  @override
  String get type => 'vad';

  @override
  Map<String, Object?> get config => settings.toJson();

  @override
  bool get inSpeech => _segment != null;

  @override
  int get _framesPending => _pending.length + (_segment?.length ?? 0);

  int get _maxSamples => _SegmenterBase._msToSamples(settings.maxSegmentMs);

  @override
  List<Segment> _step(_Frame f) {
    final segment = _segment;
    if (segment == null) return _idleStep(f);

    final out = <Segment>[];
    if (_segmentSamples + f.samples > _maxSamples) {
      // Close at the limit; the speech continues in a new segment.
      out.add(_emit(segment, forcedSplit: true));
      _segment = [];
      _segmentSamples = 0;
      _onsetIndex = 0;
      _continuation = true;
    }
    _segment!.add(f);
    _segmentSamples += f.samples;
    _silenceRun = f.isSpeech ? 0 : _silenceRun + 1;
    if (_silenceRun >= settings.hangoverFrames) {
      out.addAll(_endSegment());
      _trimPending();
    }
    return out;
  }

  List<Segment> _idleStep(_Frame f) {
    _pending.add(f);
    _speechRun = f.isSpeech ? _speechRun + 1 : 0;
    if (_speechRun < settings.onsetFrames) {
      _trimPending();
      return const [];
    }
    // Onset: the segment starts pre-roll frames before the speech run.
    final onset = _pending.length - _speechRun;
    final start = math.max(0, onset - settings.preRollFrames);
    _exclude(_pending.take(start));
    _segment = _pending.sublist(start);
    _segmentSamples = _segment!.fold(0, (sum, f) => sum + f.samples);
    _onsetIndex = onset - start;
    _silenceRun = 0;
    _continuation = false;
    _pending.clear();
    _speechRun = 0;
    return const [];
  }

  /// Keeps only frames that a future onset could use as pre-roll or as the
  /// start of its speech run; older ones are excluded.
  void _trimPending() {
    final keep = settings.preRollFrames + settings.onsetFrames - 1;
    if (_pending.length <= keep) return;
    final drop = _pending.length - keep;
    _exclude(_pending.take(drop));
    _pending.removeRange(0, drop);
  }

  /// Ends the open segment after its last speech frame plus post-roll. The
  /// silence after that returns to [_pending] (pre-roll for the next one).
  List<Segment> _endSegment() {
    final segment = _segment!;
    final lastSpeech = segment.length - 1 - _silenceRun;
    final end = math.min(
      segment.length - 1,
      lastSpeech + settings.postRollFrames,
    );
    final kept = segment.sublist(0, end + 1);
    final tail = segment.sublist(end + 1);
    final continuation = _continuation;
    final onset = _onsetIndex;
    _segment = null;
    _segmentSamples = 0;
    _silenceRun = 0;
    _continuation = false;
    _pending.addAll(tail);
    _speechRun = 0; // the tail is all non-speech

    if (kept.isEmpty) return const [];
    if (lastSpeech < 0) {
      // A continuation after a forced split that only got trailing silence.
      _exclude(kept);
      return const [];
    }
    if (!continuation) {
      final speechSamples = kept
          .sublist(onset, lastSpeech + 1)
          .fold(0, (sum, f) => sum + f.samples);
      if (speechSamples < _SegmenterBase._msToSamples(settings.minSpeechMs)) {
        _discard(kept);
        return const [];
      }
    }
    return [_emit(kept, forcedSplit: false)];
  }

  @override
  List<Segment> _flush() {
    final out = _segment == null ? const <Segment>[] : _endSegment();
    _exclude(_pending);
    _pending.clear();
    _speechRun = 0;
    return out;
  }
}
