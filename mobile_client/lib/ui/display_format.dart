/// Small display formatters (no intl dependency).
library;

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', //
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String _two(int n) => n.toString().padLeft(2, '0');

/// `Sat 18 Oct · 14:05`
String formatDateTime(DateTime t) =>
    '${_weekdays[t.weekday - 1]} ${t.day} ${_months[t.month - 1]} · '
    '${_two(t.hour)}:${_two(t.minute)}';

/// `Today`, `Yesterday` or `Sat 18 Oct 2026`, relative to [now].
String formatDay(DateTime t, DateTime now) {
  final day = DateTime(t.year, t.month, t.day);
  final today = DateTime(now.year, now.month, now.day);
  final diff = today.difference(day).inDays;
  if (diff == 0) return 'Today';
  if (diff == 1) return 'Yesterday';
  return '${_weekdays[t.weekday - 1]} ${t.day} ${_months[t.month - 1]} '
      '${t.year}';
}

/// `14:05`
String formatClock(DateTime t) => '${_two(t.hour)}:${_two(t.minute)}';

/// Milliseconds as `4.2 s`, `1 min 05 s` or `1 h 02 min`.
String formatSpan(double ms) {
  final totalSeconds = ms / 1000;
  if (totalSeconds < 60) return '${totalSeconds.toStringAsFixed(1)} s';
  final s = totalSeconds.round();
  if (s < 3600) return '${s ~/ 60} min ${_two(s % 60)} s';
  return '${s ~/ 3600} h ${_two((s % 3600) ~/ 60)} min';
}

/// Session offset as `mm:ss.s`, e.g. `01:23.4`.
String formatOffset(double ms) {
  final tenths = (ms / 100).round();
  final minutes = tenths ~/ 600;
  final seconds = (tenths % 600) / 10;
  return '${_two(minutes)}:${seconds.toStringAsFixed(1).padLeft(4, '0')}';
}

/// Bytes as `812 B`, `6.3 KB` or `1.2 MB`.
String formatBytes(int bytes) {
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

/// `1 chunk`, `3 chunks`.
String plural(int n, String one, [String? many]) =>
    '$n ${n == 1 ? one : (many ?? '${one}s')}';
