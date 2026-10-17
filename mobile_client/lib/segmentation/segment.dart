import 'dart:typed_data';

import '../capture/audio_capture.dart';
import '../capture/pcm_framer.dart';
import '../session/session_id.dart';

/// A stretch of audio selected for further processing (FR3/FR4): one or more
/// consecutive frames of a single recording run.
class Segment {
  const Segment({
    required this.seq,
    required this.run,
    required this.sessionStart,
    required this.sessionEnd,
    required this.audioStartSample,
    required this.audioEndSample,
    required this.samples,
    required this.frameCount,
    required this.speechFrameCount,
    required this.forcedSplit,
    required this.vadType,
    required this.vadConfig,
    required this.segmenterType,
    required this.segmenterConfig,
    this.sessionId,
    this.startWallClock,
    this.endWallClock,
    this.sampleRate = kSampleRate,
  });

  /// 0-based position among the session's emitted segments (discarded
  /// segments do not use a number).
  final int seq;

  /// Recording run the segment lies in (index into `RecordingSession.runs`).
  final int run;

  final String? sessionId;

  /// Offsets from session start (monotonic, pauses included).
  final Duration sessionStart;
  final Duration sessionEnd;

  /// Exact offsets on the audio timeline (pauses excluded), in samples.
  final int audioStartSample;
  final int audioEndSample;

  /// Session start wall-clock + [sessionStart] / [sessionEnd]; null when the
  /// session start wall-clock is unknown (e.g. offline WAV input).
  final DateTime? startWallClock;
  final DateTime? endWallClock;

  /// The real samples of the segment's frames (padding excluded).
  final Int16List samples;
  final int sampleRate;

  final int frameCount;

  /// Frames the VAD classified as speech (pre/post-roll frames usually are
  /// not).
  final int speechFrameCount;

  /// Ended because it reached the maximum length; the next segment continues
  /// the same speech.
  final bool forcedSplit;

  final String vadType;
  final Map<String, Object?> vadConfig;
  final String segmenterType;
  final Map<String, Object?> segmenterConfig;

  Duration get duration => samplesToDuration(samples.length, sampleRate);
  Duration get audioStart => samplesToDuration(audioStartSample, sampleRate);
  Duration get audioEnd => samplesToDuration(audioEndSample, sampleRate);

  double get speechRatio => frameCount == 0 ? 0 : speechFrameCount / frameCount;

  /// Metadata without the samples. Times in milliseconds keep microsecond
  /// precision; wall-clock times are ISO 8601 with ms and UTC offset.
  Map<String, Object?> toJson() => {
    'seq': seq,
    'session_id': sessionId,
    'run': run,
    'start_ms': _ms(sessionStart),
    'end_ms': _ms(sessionEnd),
    'duration_ms': _ms(duration),
    'audio_start_sample': audioStartSample,
    'audio_end_sample': audioEndSample,
    'audio_start_ms': _ms(audioStart),
    'audio_end_ms': _ms(audioEnd),
    'start_wallclock': startWallClock == null
        ? null
        : formatIso8601WithOffset(startWallClock!),
    'end_wallclock': endWallClock == null
        ? null
        : formatIso8601WithOffset(endWallClock!),
    'sample_rate': sampleRate,
    'samples': samples.length,
    'frames': frameCount,
    'speech_frames': speechFrameCount,
    'speech_ratio': speechRatio,
    'forced_split': forcedSplit,
    'vad': {'type': vadType, 'config': vadConfig},
    'segmenter': {'type': segmenterType, 'config': segmenterConfig},
  };

  static double _ms(Duration d) => d.inMicroseconds / 1000;

  @override
  String toString() =>
      'Segment(#$seq run $run, ${_ms(sessionStart)}–${_ms(sessionEnd)} ms, '
      'speech ${(speechRatio * 100).toStringAsFixed(0)} %'
      '${forcedSplit ? ', forced split' : ''})';
}
