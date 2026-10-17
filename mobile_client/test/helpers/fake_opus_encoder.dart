import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:echo_vault/capture/wav_writer.dart';
import 'package:echo_vault/encoding/opus_encoder.dart';

/// [OpusEncoder] that writes a small fake file instead of Opus. Records the
/// order of calls and how many run at once; calls can be held with [gates]
/// (by call number) or made to fail with [failures] (by file name).
class FakeOpusEncoder implements OpusEncoder {
  FakeOpusEncoder({this.bitrate = kDefaultOpusBitrate});

  @override
  final int bitrate;

  static const name = 'fake.opus.encoder';

  /// Output file names, in call order (retries appear again).
  final List<String> calls = [];
  final Map<int, Completer<void>> gates = {};

  /// Remaining failures per output file name.
  final Map<String, int> failures = {};

  int _active = 0;
  int maxConcurrent = 0;

  /// Waits (real time, up to 5 s) until [n] encode calls have started. The
  /// pipeline does real file I/O before each call, so a fixed number of
  /// event-loop turns is not enough.
  Future<void> untilCalls(int n) async {
    final deadline = DateTime.now().add(const Duration(seconds: 5));
    while (calls.length < n) {
      if (DateTime.now().isAfter(deadline)) {
        throw StateError('only ${calls.length} of $n encode calls started');
      }
      await Future<void>.delayed(const Duration(milliseconds: 1));
    }
  }

  @override
  Future<OpusEncoding> encode(Int16List samples, String outputPath) async {
    final call = calls.length;
    calls.add(outputPath.split('/').last);
    _active++;
    maxConcurrent = max(maxConcurrent, _active);
    try {
      if (gates[call] case final gate?) await gate.future;
      await Future<void>.delayed(Duration.zero);
      final file = File(outputPath);
      final remaining = failures[file.uri.pathSegments.last] ?? 0;
      if (remaining > 0) {
        failures[file.uri.pathSegments.last] = remaining - 1;
        file.writeAsBytesSync([1, 2, 3]); // a partial file left behind
        throw const FileSystemException('fake encoder failure');
      }
      final pcm = pcm16le(samples);
      final header = ByteData(8)
        ..setUint32(0, 0x4f676753) // "OggS"
        ..setUint32(4, samples.length);
      final bytes = Uint8List.fromList([
        ...header.buffer.asUint8List(),
        ...pcm.sublist(0, min(64, pcm.length)),
      ]);
      file.writeAsBytesSync(bytes);
      return OpusEncoding(
        encoderName: name,
        bitrate: bitrate,
        inputSamples: samples.length,
        packets: (samples.length / 320).ceil(),
        outputBytes: bytes.length,
      );
    } finally {
      _active--;
    }
  }
}
