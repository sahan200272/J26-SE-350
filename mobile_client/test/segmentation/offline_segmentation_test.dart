import 'dart:convert';
import 'dart:typed_data';

import 'package:echo_vault/capture/wav_reader.dart';
import 'package:echo_vault/capture/wav_writer.dart';
import 'package:echo_vault/segmentation/offline_segmentation.dart';
import 'package:echo_vault/segmentation/segmenter.dart';
import 'package:echo_vault/vad/energy_vad.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/signals.dart';

Uint8List wavOf(List<int> samples) => encodeWav(Int16List.fromList(samples));

void main() {
  group('readWav', () {
    test('reads what encodeWav writes', () {
      final wav = readWav(wavOf([1, -2, 32767, -32768]));
      expect(wav.sampleRate, 16000);
      expect(wav.channels, 1);
      expect(wav.bitsPerSample, 16);
      expect(wav.sampleCount, 4);
      expect(ByteData.sublistView(wav.data).getInt16(6, Endian.little), -32768);
    });

    test('skips unknown and odd-sized chunks', () {
      final plain = wavOf([5, 6, 7]);
      // Insert a 3-byte "LIST" chunk (+1 pad byte) between fmt and data.
      final extra = [...ascii('LIST'), 3, 0, 0, 0, 9, 9, 9, 0];
      final bytes = Uint8List.fromList([
        ...plain.sublist(0, 36),
        ...extra,
        ...plain.sublist(36),
      ]);
      ByteData.sublistView(bytes).setUint32(4, bytes.length - 8, Endian.little);
      expect(readWav(bytes).sampleCount, 3);
    });

    test('rejects non-WAV and non-PCM input', () {
      expect(() => readWav(Uint8List(10)), throwsFormatException);
      final float = wavOf([1, 2]);
      ByteData.sublistView(float).setUint16(20, 3, Endian.little);
      expect(() => readWav(float), throwsFormatException);
    });
  });

  group('segmentWav', () {
    final signal =
        silence(40) + tone(30) + silence(40) + tone(30) + silence(40);

    test('gives the same segments as feeding frames directly', () {
      final offline = segmentWav(wavOf(signal), VadSegmenter(EnergyVad()));
      final direct = VadSegmenter(EnergyVad());
      final expected = [
        for (final f in FrameSource().run(signal)) ...direct.add(f),
        ...direct.endRun(),
      ];
      expect(
        offline.segments.map((s) => (s.audioStartSample, s.audioEndSample)),
        expected.map((s) => (s.audioStartSample, s.audioEndSample)),
      );
      expect(offline.segments, hasLength(2));
      expect(offline.stats.isBalanced, isTrue);
      expect(offline.frameLevelsDbfs, hasLength(180));
      expect(offline.frameSpeech.where((s) => s), hasLength(60));
    });

    test('run starts split the file into runs that segments never cross', () {
      // Speech straddles sample 60·512, declared as a pause point.
      final samples = silence(40) + tone(40) + silence(40);
      final result = segmentWav(
        wavOf(samples),
        VadSegmenter(EnergyVad()),
        runStartSamples: [0, 60 * 512],
      );
      expect(result.segments.map((s) => s.run), [0, 1]);
      expect(result.segments[0].audioEndSample, 60 * 512);
      expect(result.segments[1].audioStartSample, 60 * 512);
      expect(result.segments[1].sessionStart, samplesToDurationMs(60 * 512));
    });

    test('rejects other formats and bad run starts', () {
      final stereo = wavOf(silence(2));
      ByteData.sublistView(stereo).setUint16(22, 2, Endian.little);
      expect(
        () => segmentWav(stereo, VadSegmenter(EnergyVad())),
        throwsFormatException,
      );
      expect(
        () => segmentWav(
          wavOf(silence(2)),
          VadSegmenter(EnergyVad()),
          runStartSamples: [5],
        ),
        throwsArgumentError,
      );
    });

    test('report JSON: segments in seconds, configs, summary, frames', () {
      final segmenter = FixedChunkSegmenter(EnergyVad());
      final result = segmentWav(wavOf(signal), segmenter);
      final report = offlineReport(
        result,
        segmenter,
        input: 'x.wav',
        includeFrames: true,
      );
      final decoded = jsonDecode(jsonEncode(report)) as Map<String, Object?>;
      expect(decoded['segmenter'], {
        'type': 'fixed',
        'config': {'window_ms': 5000, 'min_speech_ratio': 0.1},
      });
      expect((decoded['vad']! as Map)['type'], 'energy');
      final segs = decoded['segments']! as List;
      expect(segs, hasLength(1)); // the silent 24-frame tail is excluded
      final first = segs.first as Map;
      expect(first['start_s'], 0.0);
      expect(first['end_s'], closeTo(156 * 0.032, 1e-9));
      expect(first['speech_ratio'], closeTo(60 / 156, 1e-9));
      final summary = decoded['summary']! as Map;
      expect(summary['balanced'], isTrue);
      expect(summary['frames_seen'], 180);
      expect(summary['frame_level_dbfs_percentiles'], isA<Map>());
      expect(decoded['frames'], hasLength(180));
    });
  });

  test('percentile is nearest-rank', () {
    final v = [for (var i = 1; i <= 100; i++) i.toDouble()];
    expect(percentile(v, 50), 50);
    expect(percentile(v, 95), 95);
    expect(percentile(v, 100), 100);
    expect(percentile([3, 1, 2], 1), 1);
  });
}

List<int> ascii(String s) => s.codeUnits;

Duration samplesToDurationMs(int samples) =>
    Duration(microseconds: samples * 1000000 ~/ 16000);
