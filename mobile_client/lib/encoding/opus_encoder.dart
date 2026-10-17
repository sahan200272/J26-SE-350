import 'dart:typed_data';

/// Default Opus bitrate for 16 kHz mono speech.
const int kDefaultOpusBitrate = 32000;

/// What an encode used and produced.
class OpusEncoding {
  const OpusEncoding({
    required this.encoderName,
    required this.bitrate,
    required this.inputSamples,
    required this.packets,
    required this.outputBytes,
  });

  /// Platform codec name, e.g. `c2.android.opus.encoder`.
  final String encoderName;

  /// Requested target bitrate in bit/s.
  final int bitrate;
  final int inputSamples;

  /// Opus packets written to the file.
  final int packets;

  /// Size of the Ogg Opus file in bytes.
  final int outputBytes;

  @override
  String toString() =>
      'OpusEncoding($encoderName, $bitrate bit/s, $inputSamples samples → '
      '$packets packets, $outputBytes B)';
}

/// Encodes a segment's 16 kHz mono PCM to an Ogg Opus file (FR4).
/// Abstracted so the chunk pipeline can be tested without a platform.
/// Pure Dart.
abstract interface class OpusEncoder {
  /// Target bitrate in bit/s.
  int get bitrate;

  /// Writes [samples] as an Ogg Opus file at [outputPath].
  Future<OpusEncoding> encode(Int16List samples, String outputPath);
}
