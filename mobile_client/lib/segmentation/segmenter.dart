import 'dart:math' as math;
import 'dart:typed_data';

import '../capture/audio_capture.dart';
import '../capture/pcm_framer.dart';
import '../vad/vad.dart';
import 'segment.dart';

part 'vad_segmenter.dart';
part 'fixed_chunk_segmenter.dart';

/// Turns the frame stream of a session into [Segment]s. Pure Dart.
///
/// Feed every frame in order with [add]; call [endRun] at every pause and at
/// stop (a frame of a new run also ends the previous run). Segments never
/// cross a run boundary.
abstract interface class Segmenter {
  /// `vad` (proposed: VAD onset/offset) or `fixed` (baseline: fixed windows).
  String get type;

  /// Parameters as JSON-encodable values.
  Map<String, Object?> get config;

  /// The VAD that classifies every frame.
  Vad get vad;

  /// Inside speech: an onset has been seen and the segment is still open.
  bool get inSpeech;

  /// Decision for the most recent frame; null before the first frame.
  VadDecision? get lastDecision;

  /// Frame accounting (NFR7).
  SegmenterStats get stats;

  /// Classifies [frame] and returns the segments it completed (often none).
  List<Segment> add(PcmFrame frame);

  /// Ends the current run: closes an open segment and settles every pending
  /// frame. Returns the segments completed.
  List<Segment> endRun();
}

/// What happened to every frame (NFR7: every detected segment and every
/// excluded frame is accounted for).
///
/// After [Segmenter.endRun]: `framesSeen == framesInSegments +
/// framesInDiscardedSegments + framesExcluded` ([framesPending] is 0).
class SegmenterStats {
  const SegmenterStats({
    required this.framesSeen,
    required this.framesInSegments,
    required this.framesInDiscardedSegments,
    required this.framesExcluded,
    required this.framesPending,
    required this.speechFrames,
    required this.excludedSpeechFrames,
    required this.segmentsEmitted,
    required this.segmentsDiscarded,
    required this.forcedSplits,
    required this.samplesInSegments,
  });

  final int framesSeen;

  /// Frames inside emitted segments (including pre/post-roll).
  final int framesInSegments;

  /// Frames inside segments discarded as too short.
  final int framesInDiscardedSegments;

  /// Frames outside every segment: classified non-speech by the segmenter.
  final int framesExcluded;

  /// Frames not settled yet (held for a possible segment).
  final int framesPending;

  /// Frames the VAD classified as speech, wherever they ended up.
  final int speechFrames;

  /// Of [framesExcluded], those the VAD called speech (bursts too short for
  /// an onset, or below the speech-ratio threshold).
  final int excludedSpeechFrames;

  final int segmentsEmitted;
  final int segmentsDiscarded;
  final int forcedSplits;
  final int samplesInSegments;

  /// The NFR7 identity, including frames still pending.
  bool get isBalanced =>
      framesSeen ==
      framesInSegments +
          framesInDiscardedSegments +
          framesExcluded +
          framesPending;

  Map<String, Object?> toJson() => {
    'frames_seen': framesSeen,
    'frames_in_segments': framesInSegments,
    'frames_in_discarded_segments': framesInDiscardedSegments,
    'frames_excluded': framesExcluded,
    'frames_pending': framesPending,
    'speech_frames': speechFrames,
    'excluded_speech_frames': excludedSpeechFrames,
    'segments_emitted': segmentsEmitted,
    'segments_discarded': segmentsDiscarded,
    'forced_splits': forcedSplits,
    'samples_in_segments': samplesInSegments,
    'balanced': isBalanced,
  };

  @override
  String toString() => 'SegmenterStats(${toJson()})';
}

/// A frame with its VAD verdict.
class _Frame {
  _Frame(this.frame, this.isSpeech);

  final PcmFrame frame;
  final bool isSpeech;

  int get samples => frame.validSamples;
}

/// Shared bookkeeping: VAD classification, run boundaries, counters and
/// segment construction.
abstract class _SegmenterBase implements Segmenter {
  _SegmenterBase(this.vad, {this.sessionId, this.sessionStartWallClock});

  @override
  final Vad vad;
  final String? sessionId;
  final DateTime? sessionStartWallClock;

  int? _run;
  VadDecision? _last;

  int _framesSeen = 0;
  int _framesInSegments = 0;
  int _framesInDiscarded = 0;
  int _framesExcluded = 0;
  int _speechFrames = 0;
  int _excludedSpeech = 0;
  int _segmentsEmitted = 0;
  int _segmentsDiscarded = 0;
  int _forcedSplits = 0;
  int _samplesInSegments = 0;

  /// Frames held by the subclass, not yet settled.
  int get _framesPending;

  List<Segment> _step(_Frame f);
  List<Segment> _flush();

  @override
  VadDecision? get lastDecision => _last;

  @override
  SegmenterStats get stats => SegmenterStats(
    framesSeen: _framesSeen,
    framesInSegments: _framesInSegments,
    framesInDiscardedSegments: _framesInDiscarded,
    framesExcluded: _framesExcluded,
    framesPending: _framesPending,
    speechFrames: _speechFrames,
    excludedSpeechFrames: _excludedSpeech,
    segmentsEmitted: _segmentsEmitted,
    segmentsDiscarded: _segmentsDiscarded,
    forcedSplits: _forcedSplits,
    samplesInSegments: _samplesInSegments,
  );

  @override
  List<Segment> add(PcmFrame frame) {
    final out = <Segment>[];
    if (_run != null && frame.run != _run) out.addAll(endRun());
    _run = frame.run;
    final decision = vad.classify(frame);
    _last = decision;
    _framesSeen++;
    if (decision.isSpeech) _speechFrames++;
    out.addAll(_step(_Frame(frame, decision.isSpeech)));
    return out;
  }

  @override
  List<Segment> endRun() {
    final out = _flush();
    _run = null;
    return out;
  }

  void _exclude(Iterable<_Frame> frames) {
    for (final f in frames) {
      _framesExcluded++;
      if (f.isSpeech) _excludedSpeech++;
    }
  }

  void _discard(List<_Frame> frames) {
    _framesInDiscarded += frames.length;
    _segmentsDiscarded++;
  }

  Segment _emit(List<_Frame> frames, {required bool forcedSplit}) {
    final first = frames.first.frame;
    final last = frames.last.frame;
    final total = frames.fold(0, (sum, f) => sum + f.samples);
    final samples = Int16List(total);
    var offset = 0;
    for (final f in frames) {
      samples.setRange(offset, offset + f.samples, f.frame.samples);
      offset += f.samples;
    }
    final start = first.sessionOffset;
    final end = last.sessionOffset + last.duration;
    final wall = sessionStartWallClock;
    final segment = Segment(
      seq: _segmentsEmitted,
      run: first.run,
      sessionId: sessionId,
      sessionStart: start,
      sessionEnd: end,
      audioStartSample: first.audioOffsetSamples,
      audioEndSample: last.audioOffsetSamples + last.validSamples,
      startWallClock: wall?.add(start),
      endWallClock: wall?.add(end),
      samples: samples,
      sampleRate: first.sampleRate,
      frameCount: frames.length,
      speechFrameCount: frames.where((f) => f.isSpeech).length,
      forcedSplit: forcedSplit,
      vadType: vad.type,
      vadConfig: vad.config,
      segmenterType: type,
      segmenterConfig: config,
    );
    _segmentsEmitted++;
    _framesInSegments += frames.length;
    _samplesInSegments += total;
    if (forcedSplit) _forcedSplits++;
    return segment;
  }

  static int _msToSamples(int ms) => ms * kSampleRate ~/ 1000;
}
