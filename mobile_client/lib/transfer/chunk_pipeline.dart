import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import '../capture/pcm_framer.dart';
import '../encoding/opus_encoder.dart';
import '../segmentation/segment.dart';
import '../segmentation/segmenter.dart';
import '../session/recording_session.dart';
import 'chunk_files.dart';
import 'manifest.dart';
import 'sha256.dart';
import 'sidecar.dart';

/// Turns one session's segments into chunk files in the outbox (FR4, NFR7).
///
/// Segments are encoded strictly one at a time, in the order they were
/// added; none is dropped, however long the queue gets (its length is logged,
/// NFR8). For each segment:
///
/// 1. the encoder writes `staging/<base>.opus`;
/// 2. its SHA-256 goes into the sidecar, written to `staging/<base>.json`;
/// 3. the `.opus` is renamed into `outbox/<session_id>/`, then the `.json`.
///
/// [finish] waits for the queue, then writes the manifest the same way, last.
/// Renames within `files/` are atomic, so the synced folder never holds a
/// partial file, and a sidecar never appears before its audio.
///
/// A failed encode or write is retried once ([maxAttempts]); if it still
/// fails, the segment is listed in the manifest's `failed_chunks`.
/// Pure Dart (dart:io).
class ChunkPipeline {
  ChunkPipeline({
    required this.sessionId,
    required this.encoder,
    required this._filesDir,
    required this._appVersion,
    this.maxAttempts = 2,
    this.log,
    this.onPublished,
  });

  final String sessionId;
  final OpusEncoder encoder;
  final Future<String> _filesDir;
  final Future<String> _appVersion;
  final int maxAttempts;
  final void Function(String message)? log;

  /// Called with each file name right after it is renamed into the outbox.
  final void Function(String fileName)? onPublished;

  final _watch = Stopwatch()..start();
  final _chunks = <ChunkRecord>[];
  final _failed = <FailedChunk>[];
  final _manifest = Completer<Map<String, Object?>>();
  Future<void> _tail = Future.value();
  int _queueLength = 0;
  int _maxQueueLength = 0;
  bool _finishing = false;

  /// Segments waiting or being encoded.
  int get queueLength => _queueLength;
  int get maxQueueLength => _maxQueueLength;

  /// Chunks published so far, in order.
  List<ChunkRecord> get chunks => List.unmodifiable(_chunks);
  List<FailedChunk> get failedChunks => List.unmodifiable(_failed);

  /// Completes with the manifest once it has been published.
  Future<Map<String, Object?>> get manifest => _manifest.future;

  /// Queues [segment]; [run] is its recording run (tap offset, startup
  /// delay).
  void add(Segment segment, RecordingRun run) {
    if (_finishing) throw StateError('ChunkPipeline is finishing.');
    if (segment.sessionId != sessionId) {
      throw ArgumentError.value(segment.sessionId, 'segment.sessionId');
    }
    _queueLength++;
    _maxQueueLength = math.max(_maxQueueLength, _queueLength);
    final queued = _watch.elapsed;
    final lengthAtEnqueue = _queueLength;
    log?.call('[encode] queued #${segment.seq} (queue length $_queueLength)');
    _tail = _tail.then((_) => _process(segment, run, queued, lengthAtEnqueue));
  }

  /// Waits for every queued segment, then publishes the manifest (last).
  Future<Map<String, Object?>> finish({
    required RecordingSession session,
    required Segmenter segmenter,
    required PcmFramer framer,
  }) {
    if (_finishing) return manifest;
    _finishing = true;
    () async {
      await _tail;
      final layout = OutboxLayout(await _filesDir);
      final manifest = sessionManifest(
        session: session,
        segmenter: segmenter,
        framer: framer,
        chunks: _chunks,
        failedChunks: _failed,
        appVersion: await _appVersion,
        encoderBitrate: encoder.bitrate,
        maxQueueLength: _maxQueueLength,
      );
      final name = manifestName(sessionId);
      await _publish(layout, name, _jsonBytes(manifest));
      log?.call(
        '[outbox] $name: ${_chunks.length} chunks, '
        '${_failed.length} failed, max queue length $_maxQueueLength',
      );
      _manifest.complete(manifest);
    }().catchError((Object e, StackTrace st) {
      log?.call('[outbox] manifest failed: $e');
      _manifest.completeError(e, st);
    });
    return manifest;
  }

  Future<void> _process(
    Segment segment,
    RecordingRun run,
    Duration queued,
    int lengthAtEnqueue,
  ) async {
    final seq = segment.seq;
    try {
      final layout = OutboxLayout(await _filesDir);
      await Directory(layout.stagingDir).create(recursive: true);
      final audioName = chunkAudioName(sessionId, seq);
      final staged = '${layout.stagingDir}/$audioName';

      Object? lastError;
      for (var attempt = 1; attempt <= maxAttempts; attempt++) {
        final waited = _watch.elapsed - queued;
        final started = _watch.elapsed;
        try {
          final encoding = await encoder.encode(segment.samples, staged);
          final encodeTime = _watch.elapsed - started;
          final opusBytes = await File(staged).readAsBytes();
          final sha = sha256Hex(opusBytes);
          final sidecar = chunkSidecar(
            segment: segment,
            run: run,
            encoding: encoding,
            sha256: sha,
            appVersion: await _appVersion,
            timing: ChunkTiming(
              queueWait: waited,
              encode: encodeTime,
              queueLengthAtEnqueue: lengthAtEnqueue,
            ),
          );
          final sidecarBytes = _jsonBytes(sidecar);
          final sidecarName = chunkSidecarName(sessionId, seq);
          final stagedSidecar = '${layout.stagingDir}/$sidecarName';
          await File(stagedSidecar).writeAsBytes(sidecarBytes, flush: true);

          // Audio first, then its sidecar: a sidecar never precedes its file.
          await _rename(layout, staged, audioName);
          await _rename(layout, stagedSidecar, sidecarName);

          _chunks.add(
            ChunkRecord(
              seq: seq,
              audioFile: audioName,
              sidecarFile: sidecarName,
              sha256: sha,
              sidecarSha256: sha256Hex(sidecarBytes),
              opusBytes: opusBytes.length,
              run: segment.run,
              start: segment.sessionStart,
              end: segment.sessionEnd,
              samples: segment.samples.length,
              frames: segment.frameCount,
              encoderName: encoding.encoderName,
              bitrate: encoding.bitrate,
            ),
          );
          log?.call(
            '[encode] #$seq → $audioName: ${opusBytes.length} B from '
            '${segment.samples.length} samples, ${encoding.encoderName} '
            '@ ${encoding.bitrate} bit/s, encode '
            '${encodeTime.inMilliseconds} ms (queue length ${_queueLength - 1})',
          );
          return;
        } catch (e) {
          lastError = e;
          log?.call('[encode] #$seq attempt $attempt failed: $e');
          await _deleteIfExists(staged);
        }
      }
      _failed.add(FailedChunk(seq, '$lastError'));
    } catch (e) {
      log?.call('[encode] #$seq failed: $e');
      _failed.add(FailedChunk(seq, '$e'));
    } finally {
      _queueLength--;
    }
  }

  Future<void> _publish(
    OutboxLayout layout,
    String name,
    Uint8List bytes,
  ) async {
    await Directory(layout.stagingDir).create(recursive: true);
    final staged = '${layout.stagingDir}/$name';
    await File(staged).writeAsBytes(bytes, flush: true);
    await _rename(layout, staged, name);
  }

  Future<void> _rename(OutboxLayout layout, String staged, String name) async {
    final dir = Directory(layout.sessionDir(sessionId));
    await dir.create(recursive: true);
    await File(staged).rename('${dir.path}/$name');
    onPublished?.call(name);
  }

  static Future<void> _deleteIfExists(String path) async {
    final file = File(path);
    if (await file.exists()) await file.delete();
  }

  static Uint8List _jsonBytes(Map<String, Object?> json) => Uint8List.fromList(
    utf8.encode('${const JsonEncoder.withIndent('  ').convert(json)}\n'),
  );
}
