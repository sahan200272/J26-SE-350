import 'dart:typed_data';

/// PCM data and format of a WAV file.
class WavPcm {
  const WavPcm({
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    required this.data,
  });

  final int sampleRate;
  final int channels;
  final int bitsPerSample;

  /// The `data` chunk (little-endian samples).
  final Uint8List data;

  int get sampleCount => data.length ~/ (channels * bitsPerSample ~/ 8);
}

/// Parses a RIFF/WAVE file with an uncompressed PCM `fmt ` chunk (format 1).
/// Unknown chunks are skipped. Throws [FormatException] otherwise. Pure Dart.
WavPcm readWav(Uint8List bytes) {
  final b = ByteData.sublistView(bytes);
  String tag(int at) => String.fromCharCodes(bytes.sublist(at, at + 4));
  if (bytes.length < 12 || tag(0) != 'RIFF' || tag(8) != 'WAVE') {
    throw const FormatException('Not a RIFF/WAVE file.');
  }
  int? format, channels, sampleRate, bits;
  Uint8List? data;
  var pos = 12;
  while (pos + 8 <= bytes.length) {
    final id = tag(pos);
    final size = b.getUint32(pos + 4, Endian.little);
    final body = pos + 8;
    final end = body + size;
    if (end > bytes.length) {
      throw FormatException('Chunk "$id" runs past the end of the file.');
    }
    if (id == 'fmt ') {
      format = b.getUint16(body, Endian.little);
      channels = b.getUint16(body + 2, Endian.little);
      sampleRate = b.getUint32(body + 4, Endian.little);
      bits = b.getUint16(body + 14, Endian.little);
    } else if (id == 'data') {
      data = Uint8List.sublistView(bytes, body, end);
    }
    pos = end + (size.isOdd ? 1 : 0); // chunks are word-aligned
  }
  if (format == null || data == null) {
    throw const FormatException('Missing "fmt " or "data" chunk.');
  }
  if (format != 1) {
    throw FormatException('Not PCM (format $format).');
  }
  return WavPcm(
    sampleRate: sampleRate!,
    channels: channels!,
    bitsPerSample: bits!,
    data: data,
  );
}
