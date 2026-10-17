import 'dart:math';

import 'package:echo_vault/session/session_id.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_random.dart';

final sessionIdPattern = RegExp(r'^\d{8}T\d{6}_[0-9a-f]{4}$');
final iso8601WithOffset = RegExp(
  r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$',
);

void main() {
  group('session ID (YYYYMMDDTHHMMSS_xxxx)', () {
    test('matches the CLAUDE.md example format', () {
      final id = generateSessionId(
        DateTime(2026, 10, 14, 14, 23, 0),
        FakeRandom(0xa1b2),
      );
      expect(id, '20261014T142300_a1b2');
      expect(id, matches(sessionIdPattern));
    });

    test('suffix is 4 lowercase hex digits drawn from 16 random bits', () {
      final rng = FakeRandom(0x00f);
      final id = generateSessionId(DateTime(2026, 1, 2, 3, 4, 5), rng);
      expect(id, '20260102T030405_000f');
      expect(rng.maxes, [1 << 16]);
      expect(
        generateSessionId(
          DateTime(2026, 12, 31, 23, 59, 59),
          FakeRandom(0xffff),
        ),
        '20261231T235959_ffff',
      );
    });

    test('real random suffixes always match the pattern', () {
      final rng = Random(7);
      for (var i = 0; i < 500; i++) {
        expect(
          generateSessionId(DateTime.now(), rng),
          matches(sessionIdPattern),
        );
      }
    });

    test('uses the local fields of the start time (no UTC conversion)', () {
      final local = DateTime(2026, 10, 15, 0, 30, 0);
      expect(formatCompactTimestamp(local), '20261015T003000');
    });
  });

  group('ISO 8601 with milliseconds and UTC offset', () {
    test('UTC times get +00:00', () {
      expect(
        formatIso8601WithOffset(DateTime.utc(2026, 10, 14, 8, 53, 0, 7)),
        '2026-10-14T08:53:00.007+00:00',
      );
    });

    test('local times carry the machine offset', () {
      final t = DateTime(2026, 10, 15, 9, 42, 5, 123);
      final s = formatIso8601WithOffset(t);
      expect(s, matches(iso8601WithOffset));
      expect(s, startsWith('2026-10-15T09:42:05.123'));
      expect(s, endsWith(formatUtcOffset(t.timeZoneOffset)));
      // The string and its offset identify the same instant.
      expect(DateTime.parse(s).isAtSameMomentAs(t), isTrue);
    });

    test('offset formatting, including half hours and negatives', () {
      expect(formatUtcOffset(const Duration(hours: 5, minutes: 30)), '+05:30');
      expect(formatUtcOffset(Duration.zero), '+00:00');
      expect(
        formatUtcOffset(const Duration(hours: -3, minutes: -30)),
        '-03:30',
      );
      expect(formatUtcOffset(const Duration(hours: 14)), '+14:00');
      expect(
        formatUtcOffset(const Duration(hours: -9, minutes: -30)),
        '-09:30',
      );
    });
  });
}
