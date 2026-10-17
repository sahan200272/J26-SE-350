import 'dart:typed_data';

import 'package:flutter/services.dart';

import '../capture/audio_capture.dart';
import '../capture/wav_writer.dart';
import '../platform/app_channel.dart';
import 'opus_encoder.dart';

/// [OpusEncoder] backed by `MainActivity.encodeOpus`: the platform MediaCodec
/// Opus encoder and MediaMuxer (Ogg), run off the main thread on Android.
class MethodChannelOpusEncoder implements OpusEncoder {
  const MethodChannelOpusEncoder({this.bitrate = kDefaultOpusBitrate});

  @override
  final int bitrate;

  @override
  Future<OpusEncoding> encode(Int16List samples, String outputPath) async {
    final reply = await appChannel.invokeMapMethod<String, Object?>(
      'encodeOpus',
      {
        'pcm': pcm16le(samples),
        'sampleRate': kSampleRate,
        'channels': kChannels,
        'bitrate': bitrate,
        'outputPath': outputPath,
      },
    );
    if (reply == null) {
      throw PlatformException(code: 'ENCODE_FAILED', message: 'no reply');
    }
    return OpusEncoding(
      encoderName: reply['encoder']! as String,
      bitrate: reply['bitrate']! as int,
      inputSamples: reply['inputSamples']! as int,
      packets: reply['packets']! as int,
      outputBytes: reply['outputBytes']! as int,
    );
  }
}
