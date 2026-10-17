import '../capture/audio_capture.dart';
import '../capture/pcm_framer.dart';
import '../segmentation/segmenter.dart';
import '../session/recording_session.dart';
import '../session/session_id.dart';

/// Manifest schema.
const kManifestSchema = 'c1-manifest/0.1';

/// One chunk as listed in the manifest.
class ChunkRecord {
  const ChunkRecord({
    required this.seq,
    required this.audioFile,
    required this.sidecarFile,
    required this.sha256,
    required this.sidecarSha256,
    required this.opusBytes,
    required this.run,
    required this.start,
    required this.end,
    required this.samples,
    required this.frames,
    required this.encoderName,
    required this.bitrate,
  });

  final int seq;
  final String audioFile;
  final String sidecarFile;

  /// SHA-256 of the `.opus` file (as in its sidecar).
  final String sha256;

  /// SHA-256 of the `.json` sidecar.
  final String sidecarSha256;
  final int opusBytes;
  final int run;

  /// Session offsets.
  final Duration start;
  final Duration end;
  final int samples;
  final int frames;
  final String encoderName;
  final int bitrate;

  Map<String, Object?> toJson() => {
    'seq': seq,
    'audio_file': audioFile,
    'sidecar_file': sidecarFile,
    'sha256': sha256,
    'sidecar_sha256': sidecarSha256,
    'opus_bytes': opusBytes,
    'run': run,
    'start_ms': _ms(start),
    'end_ms': _ms(end),
    'samples': samples,
    'frames': frames,
  };
}

/// A segment that could not be encoded or written (after retrying). Listed
/// so that the PC sees the gap in `seqs` explained (NFR7).
class FailedChunk {
  const FailedChunk(this.seq, this.error);

  final int seq;
  final String error;

  Map<String, Object?> toJson() => {'seq': seq, 'error': error};
}

/// The `<session_id>_manifest.json` written on Stop, after every chunk.
Map<String, Object?> sessionManifest({
  required RecordingSession session,
  required Segmenter segmenter,
  required PcmFramer framer,
  required List<ChunkRecord> chunks,
  required List<FailedChunk> failedChunks,
  required String appVersion,
  required int encoderBitrate,
  required int maxQueueLength,
}) {
  final sorted = List.of(chunks)..sort((a, b) => a.seq.compareTo(b.seq));
  final start = session.startWallClock!;
  final end = session.stoppedOffset ?? session.totalDuration;
  final stats = segmenter.stats;
  return {
    'schema_version': kManifestSchema,
    'session_id': session.id,
    'app_version': appVersion,
    'session_start_wallclock': formatIso8601WithOffset(start),
    'session_end_wallclock': formatIso8601WithOffset(start.add(end)),
    'session_start_ms': 0.0,
    'session_end_ms': _ms(end),
    'recorded_ms': _ms(session.recordedDuration),
    'sample_rate': kSampleRate,
    'channels': kChannels,
    'chunk_count': sorted.length,
    'seqs': [for (final c in sorted) c.seq],
    'chunks': [for (final c in sorted) c.toJson()],
    'failed_chunks': [for (final f in failedChunks) f.toJson()],
    'pause_intervals': [
      for (final p in session.pauseIntervals)
        {
          'start_ms': _ms(p.start),
          'end_ms': p.end == null ? null : _ms(p.end!),
          'reason': p.reason.wireName,
        },
    ],
    'runs': [
      for (final (i, r) in session.runs.indexed)
        {
          'index': i,
          'tap_offset_ms': _ms(r.startOffset),
          'startup_delay_ms': _optMs(r.captureStartDelay),
          'capture_start_ms': _optMs(r.captureStartOffset),
        },
    ],
    'frame_accounting': stats.toJson(),
    'capture': {
      'frames_emitted': framer.framesEmitted,
      'padded_frames': framer.paddedFrames,
      'samples_framed': framer.samplesFramed,
      'dropped_bytes': framer.droppedBytes,
      'dropped_chunks': framer.droppedChunks,
      'odd_bytes_discarded': framer.discardedOddBytes,
    },
    'segmenter': {'type': segmenter.type, 'config': segmenter.config},
    'vad': {'type': segmenter.vad.type, 'config': segmenter.vad.config},
    'encoder': {
      'name': sorted.isEmpty ? null : sorted.first.encoderName,
      'bitrate': encoderBitrate,
    },
    'encode_queue': {'max_length': maxQueueLength},
  };
}

double _ms(Duration d) => d.inMicroseconds / 1000;
double? _optMs(Duration? d) => d == null ? null : _ms(d);
