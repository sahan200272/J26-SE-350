import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'audio_capture.dart';
import 'pcm_framer.dart';

/// Receives every frame of one session, in order.
abstract interface class FrameSink {
  void add(PcmFrame frame);

  /// Called once, after the last frame of the session.
  Future<void> close();
}

/// Writes the real (unpadded) samples of each frame to a 16-bit PCM WAV
/// file. Used only in debug builds to verify the captured format.
///
/// Writes are queued, so [add] never blocks; [close] waits for them, then
/// fills in the RIFF and data sizes. Pure Dart (dart:io, no Flutter).
class WavFileWriter implements FrameSink {
  /// Opens [path] (creating parent folders) once [path] completes.
  WavFileWriter(
    Future<String> path, {
    this.sampleRate = kSampleRate,
    this.channels = kChannels,
    this.log,
  }) {
    _queue = path
        .then((p) async {
          _path = p;
          final file = File(p);
          await file.parent.create(recursive: true);
          final raf = await file.open(mode: FileMode.write);
          _file = raf;
          await raf.writeFrom(_header(0));
        })
        .catchError(_recordError);
  }

  final int sampleRate;
  final int channels;
  final void Function(String message)? log;

  static const int _bytesPerSample = 2;
  static const int _headerBytes = 44;

  late Future<void> _queue;
  RandomAccessFile? _file;
  String? _path;
  int _dataBytes = 0;
  bool _closed = false;
  Object? _error;

  /// Samples queued so far.
  int get samplesWritten => _dataBytes ~/ _bytesPerSample;

  /// File path, once known.
  String? get path => _path;

  @override
  void add(PcmFrame frame) {
    if (_closed) throw StateError('WavFileWriter is closed.');
    if (frame.validSamples == 0) return;
    final bytes = Uint8List(frame.validSamples * _bytesPerSample);
    final data = ByteData.sublistView(bytes);
    for (var i = 0; i < frame.validSamples; i++) {
      data.setInt16(i * _bytesPerSample, frame.samples[i], Endian.little);
    }
    _dataBytes += bytes.length;
    _enqueue((raf) => raf.writeFrom(bytes));
  }

  @override
  Future<void> close() async {
    if (_closed) return _queue;
    _closed = true;
    final dataBytes = _dataBytes;
    _enqueue((raf) async {
      await raf.setPosition(0);
      await raf.writeFrom(_header(dataBytes));
      await raf.close();
      _file = null;
    });
    await _queue;
    if (_error case final error?) {
      await _file?.close().catchError(_recordError);
      _file = null;
      log?.call('[wav] $_path: write failed: $error');
    } else {
      log?.call(
        '[wav] wrote $_path: ${dataBytes ~/ _bytesPerSample} samples, '
        '${dataBytes + _headerBytes} bytes',
      );
    }
  }

  void _enqueue(Future<void> Function(RandomAccessFile raf) op) {
    _queue = _queue
        .then((_) {
          final raf = _file;
          if (raf == null || _error != null) return null;
          return op(raf);
        })
        .catchError(_recordError);
  }

  void _recordError(Object e) => _error ??= e;

  Uint8List _header(int dataBytes) =>
      wavHeader(dataBytes, sampleRate: sampleRate, channels: channels);
}

/// Canonical 44-byte 16-bit PCM WAV header for [dataBytes] of sample data.
Uint8List wavHeader(
  int dataBytes, {
  int sampleRate = kSampleRate,
  int channels = kChannels,
}) {
  const bytesPerSample = 2;
  final blockAlign = channels * bytesPerSample;
  final h = ByteData(44);
  void ascii(int offset, String s) {
    for (var i = 0; i < s.length; i++) {
      h.setUint8(offset + i, s.codeUnitAt(i));
    }
  }

  ascii(0, 'RIFF');
  h.setUint32(4, 36 + dataBytes, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  h.setUint32(16, 16, Endian.little); // fmt chunk size
  h.setUint16(20, 1, Endian.little); // PCM
  h.setUint16(22, channels, Endian.little);
  h.setUint32(24, sampleRate, Endian.little);
  h.setUint32(28, sampleRate * blockAlign, Endian.little); // byte rate
  h.setUint16(32, blockAlign, Endian.little);
  h.setUint16(34, bytesPerSample * 8, Endian.little); // bits per sample
  ascii(36, 'data');
  h.setUint32(40, dataBytes, Endian.little);
  return h.buffer.asUint8List();
}

/// A complete mono 16-bit PCM WAV file holding [samples].
Uint8List encodeWav(Int16List samples, {int sampleRate = kSampleRate}) {
  final out = BytesBuilder(copy: false)
    ..add(wavHeader(samples.length * 2, sampleRate: sampleRate))
    ..add(_pcm16le(samples));
  return out.takeBytes();
}

Uint8List _pcm16le(Int16List samples) {
  final bytes = Uint8List(samples.length * 2);
  final data = ByteData.sublistView(bytes);
  for (var i = 0; i < samples.length; i++) {
    data.setInt16(i * 2, samples[i], Endian.little);
  }
  return bytes;
}

/// Writes [samples] as a WAV file at [path], creating parent folders.
Future<void> writeWavFile(
  String path,
  Int16List samples, {
  int sampleRate = kSampleRate,
}) async {
  final file = File(path);
  await file.parent.create(recursive: true);
  await file.writeAsBytes(encodeWav(samples, sampleRate: sampleRate));
}
