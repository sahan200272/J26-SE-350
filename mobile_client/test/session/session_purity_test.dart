import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

final _flutterImport = RegExp(r'''import\s+['"](package:flutter|dart:ui)''');

void expectNoFlutterImports(Iterable<File> files) {
  expect(files, isNotEmpty);
  for (final f in files) {
    expect(
      _flutterImport.hasMatch(f.readAsStringSync()),
      isFalse,
      reason: '${f.path} imports Flutter',
    );
  }
}

/// Session, capture, VAD and segmentation logic must stay pure Dart
/// (CLAUDE.md): no Flutter or dart:ui imports, so it can run offline on WAV
/// files.
void main() {
  test('lib/session has no Flutter imports', () {
    expectNoFlutterImports(
      Directory('lib/session')
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('.dart')),
    );
  });

  for (final dir in ['lib/vad', 'lib/segmentation']) {
    test('$dir has no Flutter imports', () {
      expectNoFlutterImports(
        Directory(dir)
            .listSync(recursive: true)
            .whereType<File>()
            .where((f) => f.path.endsWith('.dart')),
      );
    });
  }

  test('pure lib/capture files have no Flutter imports', () {
    // record_audio_capture.dart is the plugin adapter and may use Flutter.
    expectNoFlutterImports([
      for (final name in [
        'audio_capture.dart',
        'pcm_framer.dart',
        'level_meter.dart',
        'wav_writer.dart',
        'wav_reader.dart',
      ])
        File('lib/capture/$name'),
    ]);
  });
}
