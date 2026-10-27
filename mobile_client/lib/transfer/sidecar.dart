import '../capture/audio_capture.dart';
import '../encoding/opus_encoder.dart';
import '../segmentation/segment.dart';
import '../session/recording_session.dart';
import '../session/session_id.dart';
import 'chunk_files.dart';

/// Sidecar schema (CLAUDE.md).
const kChunkSchema = 'c1-chunk/0.1';

/// Processing times of one chunk (FR12, NFR8).
class ChunkTiming {
  const ChunkTiming({
    required this.queueWait,
    required this.encode,
    required this.queueLengthAtEnqueue,
  });

  /// From the segment entering the queue to its encode starting.
  final Duration queueWait;

  /// The platform encode call.
  final Duration encode;

  /// Segments waiting or encoding when this one was queued (itself
  /// included).
  final int queueLengthAtEnqueue;

  Map<String, Object?> toJson() => {
    'queue_wait_ms': _ms(queueWait),
    'encode_ms': _ms(encode),
    'queue_length_at_enqueue': queueLengthAtEnqueue,
  };
}

/// The `<session_id>_<seq:05d>.json` sidecar of one encoded segment.
///
/// The `c1-chunk/0.1` fields of CLAUDE.md, plus the run, the segmenter, the
/// original sample count, the encoder and processing times. Times are
/// milliseconds with microsecond precision; wall-clock times are ISO 8601
/// with ms and UTC offset. No device identifiers, names or location.
Map<String, Object?> chunkSidecar({
  required Segment segment,
  required RecordingRun run,
  required OpusEncoding encoding,
  required String sha256,
  required String appVersion,
  required ChunkTiming timing,
}) {
  final sessionId = segment.sessionId!;
  return {
    // c1-chunk/0.1 (CLAUDE.md)
    'schema_version': kChunkSchema,
    'session_id': sessionId,
    'seq': segment.seq,
    'audio_file': chunkAudioName(sessionId, segment.seq),
    'codec': 'opus',
    'sample_rate': kSampleRate,
    'channels': kChannels,
    'start_ms': _ms(segment.sessionStart),
    'end_ms': _ms(segment.sessionEnd),
    'start_wallclock': _wall(segment.startWallClock),
    'end_wallclock': _wall(segment.endWallClock),
    'duration_ms': _ms(segment.duration),
    'vad': {'type': segment.vadType, 'config': segment.vadConfig},
    'app_version': appVersion,
    'sha256': sha256,
    // A4 additions
    'container': 'ogg',
    'run': segment.run,
    'run_tap_offset_ms': _ms(run.startOffset),
    'run_startup_delay_ms': _optMs(run.captureStartDelay),
    'run_capture_start_ms': _optMs(run.captureStartOffset),
    'segmenter': {
      'type': segment.segmenterType,
      'config': segment.segmenterConfig,
    },
    'speech_ratio': segment.speechRatio,
    'frames': segment.frameCount,
    'speech_frames': segment.speechFrameCount,
    'samples': segment.samples.length,
    'audio_start_sample': segment.audioStartSample,
    'audio_end_sample': segment.audioEndSample,
    'forced_split': segment.forcedSplit,
    'encoder': {'name': encoding.encoderName, 'bitrate': encoding.bitrate},
    'opus_bytes': encoding.outputBytes,
    'opus_packets': encoding.packets,
    'processing': timing.toJson(),
  };
}

double _ms(Duration d) => d.inMicroseconds / 1000;
double? _optMs(Duration? d) => d == null ? null : _ms(d);
String? _wall(DateTime? t) => t == null ? null : formatIso8601WithOffset(t);
