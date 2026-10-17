import 'dart:math';

/// Session ID as in CLAUDE.md: local start time plus a 4-hex-digit random
/// suffix, e.g. `20261014T142300_a1b2`.
String generateSessionId(DateTime localStart, Random random) {
  final suffix = random.nextInt(1 << 16).toRadixString(16).padLeft(4, '0');
  return '${formatCompactTimestamp(localStart)}_$suffix';
}

/// `YYYYMMDDTHHMMSS` from [t]'s own fields (no time zone conversion).
String formatCompactTimestamp(DateTime t) =>
    '${_pad(t.year, 4)}${_pad(t.month)}${_pad(t.day)}'
    'T${_pad(t.hour)}${_pad(t.minute)}${_pad(t.second)}';

/// ISO 8601 with milliseconds and the UTC offset of [t], e.g.
/// `2026-10-14T14:23:00.123+05:30`. A UTC [t] gets `+00:00`.
String formatIso8601WithOffset(DateTime t) =>
    '${_pad(t.year, 4)}-${_pad(t.month)}-${_pad(t.day)}'
    'T${_pad(t.hour)}:${_pad(t.minute)}:${_pad(t.second)}'
    '.${_pad(t.millisecond, 3)}${formatUtcOffset(t.timeZoneOffset)}';

/// `+HH:MM` / `-HH:MM`.
String formatUtcOffset(Duration offset) {
  final sign = offset.isNegative ? '-' : '+';
  final minutes = offset.inMinutes.abs();
  return '$sign${_pad(minutes ~/ 60)}:${_pad(minutes % 60)}';
}

String _pad(int n, [int width = 2]) => n.toString().padLeft(width, '0');
