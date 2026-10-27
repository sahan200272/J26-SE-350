import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:echo_vault/transfer/sha256.dart';
import 'package:flutter_test/flutter_test.dart';

String hashOf(String s) => sha256Hex(Uint8List.fromList(utf8.encode(s)));

void main() {
  group('FIPS 180-2 test vectors', () {
    test('empty message', () {
      expect(
        hashOf(''),
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      );
    });

    test('"abc" (one block)', () {
      expect(
        hashOf('abc'),
        'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
      );
    });

    test('448-bit message (padding spills into a second block)', () {
      expect(
        hashOf('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'),
        '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1',
      );
    });

    test('one million "a"', () {
      expect(
        sha256Hex(Uint8List(1000000)..fillRange(0, 1000000, 0x61)),
        'cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0',
      );
    });
  });

  test('matches the system sha256sum at block-boundary lengths', () {
    // Cross-check against an independent implementation where one exists
    // (Git for Windows, Linux, macOS ship sha256sum / shasum).
    final tool = ['sha256sum', 'shasum'].firstWhere((t) {
      try {
        return Process.runSync(t, ['--version']).exitCode == 0;
      } on ProcessException {
        return false;
      }
    }, orElse: () => '');
    if (tool.isEmpty) {
      markTestSkipped('no sha256sum/shasum on PATH');
      return;
    }
    final dir = Directory.systemTemp.createTempSync('sha256');
    addTearDown(() => dir.deleteSync(recursive: true));
    for (final n in [0, 1, 55, 56, 63, 64, 65, 119, 120, 200, 4099]) {
      final data = Uint8List.fromList([
        for (var i = 0; i < n; i++) (i * 31 + 7) & 0xff,
      ]);
      final file = File('${dir.path}/d$n')..writeAsBytesSync(data);
      final args = tool == 'shasum' ? ['-a', '256', file.path] : [file.path];
      // Git for Windows prefixes "\" for paths with backslashes.
      final expected = RegExp('[0-9a-f]{64}')
          .firstMatch(Process.runSync(tool, args).stdout as String)![0];
      expect(sha256Hex(data), expected, reason: 'length $n');
    }
  });
}
