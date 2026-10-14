import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// lib/session must stay pure Dart (CLAUDE.md): no Flutter or dart:ui imports.
void main() {
  test('lib/session has no Flutter imports', () {
    final files = Directory('lib/session')
        .listSync(recursive: true)
        .whereType<File>()
        .where((f) => f.path.endsWith('.dart'))
        .toList();
    expect(files, isNotEmpty);
    final forbidden = RegExp(r'''import\s+['"](package:flutter|dart:ui)''');
    for (final f in files) {
      expect(
        forbidden.hasMatch(f.readAsStringSync()),
        isFalse,
        reason: '${f.path} imports Flutter',
      );
    }
  });
}
