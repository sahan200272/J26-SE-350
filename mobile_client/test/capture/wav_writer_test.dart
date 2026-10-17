import 'dart:io';
import 'dart:typed_data';

import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/capture/wav_writer.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/pcm.dart';

void main() {
  late Directory tmp;

  setUp(() => tmp = Directory.systemTemp.createTempSync('echo_vault_wav'));
  tearDown(() => tmp.deleteSync(recursive: true));

  String ascii(Uint8List b, int at) =>
      String.fromCharCodes(b.sublist(at, at + 4));

  test(
    'writes a 16 kHz mono 16-bit PCM WAV of the real samples only',
    () async {
      final logs = <String>[];
      final path = '${tmp.path}/debug/20261015T094200_00ff.wav';
      final writer = WavFileWriter(Future.value(path), log: logs.add);

      // 1000 samples framed as 512 + a padded 488.
      final source = rampSamples(1000);
      final framer = PcmFramer()..open(Duration.zero);
      final frames = framer.add(pcmBytes(source))..addAll(framer.close());
      expect(frames.last.isPadded, isTrue);
      frames.forEach(writer.add);
      await writer.close();

      final bytes = File(path).readAsBytesSync();
      final h = ByteData.sublistView(bytes);
      expect(bytes.length, 44 + 2000, reason: 'padding must not be written');
      expect(ascii(bytes, 0), 'RIFF');
      expect(h.getUint32(4, Endian.little), 36 + 2000);
      expect(ascii(bytes, 8), 'WAVE');
      expect(ascii(bytes, 12), 'fmt ');
      expect(h.getUint32(16, Endian.little), 16);
      expect(h.getUint16(20, Endian.little), 1, reason: 'PCM');
      expect(h.getUint16(22, Endian.little), 1, reason: 'mono');
      expect(h.getUint32(24, Endian.little), 16000);
      expect(h.getUint32(28, Endian.little), 32000, reason: 'byte rate');
      expect(h.getUint16(32, Endian.little), 2, reason: 'block align');
      expect(h.getUint16(34, Endian.little), 16, reason: 'bits');
      expect(ascii(bytes, 36), 'data');
      expect(h.getUint32(40, Endian.little), 2000);
      expect(bytes.sublist(44), pcmBytes(source));

      expect(writer.samplesWritten, 1000);
      expect(writer.path, path);
      expect(logs.single, contains('1000 samples'));
    },
  );

  test('an empty session gives a valid header-only file', () async {
    final path = '${tmp.path}/empty.wav';
    final writer = WavFileWriter(Future.value(path));
    await writer.close();
    final bytes = File(path).readAsBytesSync();
    expect(bytes.length, 44);
    expect(ByteData.sublistView(bytes).getUint32(40, Endian.little), 0);
  });

  test('frames added before the path is known are kept, in order', () async {
    final path = '${tmp.path}/late.wav';
    final writer = WavFileWriter(
      Future.delayed(const Duration(milliseconds: 20), () => path),
    );
    final framer = PcmFramer()..open(Duration.zero);
    final source = rampSamples(2048);
    framer.add(pcmBytes(source)).forEach(writer.add);
    await writer.close();
    expect(File(path).readAsBytesSync().sublist(44), pcmBytes(source));
  });

  test('a failing path is logged, not thrown', () async {
    final logs = <String>[];
    final writer = WavFileWriter(
      Future.error(const FileSystemException('no files dir')),
      log: logs.add,
    );
    final framer = PcmFramer()..open(Duration.zero);
    framer.add(constantPcm(512)).forEach(writer.add);
    await writer.close();
    expect(logs.single, contains('write failed'));
  });
}
