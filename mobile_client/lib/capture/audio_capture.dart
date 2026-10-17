import 'dart:typed_data';

/// Internal audio format (CLAUDE.md): 16 kHz, mono, 16-bit little-endian PCM.
const int kSampleRate = 16000;
const int kChannels = 1;

/// Microphone PCM source. Abstracted so the session logic and UI can be
/// tested without a platform.
///
/// [pause] and [stop] must stop capture at the source (FR2); [resume] starts
/// it again. Callers must still treat bytes that arrive after [pause] or
/// [stop] as not recorded: data already in flight can be delivered late.
abstract interface class AudioCapture {
  /// PCM16LE mono bytes at [kSampleRate]. Chunk sizes are arbitrary (a chunk
  /// may even split a sample). Errors report capture failures.
  Stream<Uint8List> get pcm;

  Future<void> start();
  Future<void> pause();
  Future<void> resume();
  Future<void> stop();
}

/// Capture ended or changed format without being asked to.
class CaptureFailure implements Exception {
  const CaptureFailure(this.message);

  final String message;

  @override
  String toString() => 'CaptureFailure: $message';
}
