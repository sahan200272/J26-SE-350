/// Checks for what the user types on the Settings screen: the PC's Syncthing
/// device ID and its LAN address. Pure Dart (no Flutter imports).
///
/// The app re-checks both natively (Syncthing's `/rest/svc/deviceid`, and a
/// private-IPv4 check), so these are for immediate feedback.
library;

const int kSyncthingPort = 22000;

const _base32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

/// Returns [input] as a canonical Syncthing device ID (`XXXXXXX-…`, 8 groups
/// of 7), or throws a [FormatException] saying what is wrong.
///
/// Accepts what Syncthing accepts (`lib/protocol/deviceid.go`): upper or lower
/// case, with or without `-`/spaces, the typos `0`→`O`, `1`→`I`, `8`→`B`, and
/// 56 characters (four 13-character groups, each followed by its check
/// character) or the old 52 characters without check characters.
String normalizeDeviceId(String input) {
  final s = input
      .trim()
      .toUpperCase()
      .replaceAll('0', 'O')
      .replaceAll('1', 'I')
      .replaceAll('8', 'B')
      .replaceAll(RegExp(r'[-\s]'), '');
  if (s.isEmpty) throw const FormatException('Enter the PC’s device ID');
  for (final char in s.split('')) {
    if (!_base32.contains(char)) {
      throw FormatException('Device IDs use only A–Z and 2–7, not “$char”');
    }
  }
  final String withChecks;
  if (s.length == 56) {
    for (var group = 0; group < 4; group++) {
      final data = s.substring(group * 14, group * 14 + 13);
      if (s[group * 14 + 13] != _luhnBase32(data)) {
        throw const FormatException(
          'Device ID has a typo (check character does not match)',
        );
      }
    }
    withChecks = s;
  } else if (s.length == 52) {
    withChecks = [
      for (var group = 0; group < 4; group++)
        s.substring(group * 13, group * 13 + 13) +
            _luhnBase32(s.substring(group * 13, group * 13 + 13)),
    ].join();
  } else {
    throw FormatException(
      'Device ID has ${s.length} characters; expected 56 (without dashes)',
    );
  }
  return [for (var i = 0; i < 56; i += 7) withChecks.substring(i, i + 7)]
      .join('-');
}

/// Syncthing's check character: a Luhn mod-32 variant whose factor starts at
/// 1 on the left (`luhnBase32` in Syncthing; it deliberately differs from the
/// textbook algorithm).
String _luhnBase32(String data) {
  var factor = 1;
  var sum = 0;
  for (final char in data.split('')) {
    var addend = factor * _base32.indexOf(char);
    factor = factor == 2 ? 1 : 2;
    addend = addend ~/ 32 + addend % 32;
    sum += addend;
  }
  return _base32[(32 - sum % 32) % 32];
}

/// Returns the fixed Syncthing address `tcp://<ip>:<port>` for what the user
/// typed (`192.168.1.20`, `192.168.1.20:22000` or `tcp://192.168.1.20:22000`),
/// or throws a [FormatException].
///
/// LAN only: the address must be a private (RFC 1918: 10/8, 172.16/12,
/// 192.168/16) or link-local (169.254/16) IPv4 address. Host names are not
/// accepted (the phone's Syncthing does no DNS lookups).
String lanAddress(String input) {
  var s = input.trim();
  if (s.isEmpty) throw const FormatException('Enter the PC’s IP address');
  if (s.toLowerCase().startsWith('tcp://')) s = s.substring(6);
  var port = kSyncthingPort;
  final colon = s.indexOf(':');
  if (colon >= 0) {
    port = int.tryParse(s.substring(colon + 1)) ?? -1;
    if (port < 1 || port > 65535) {
      throw const FormatException('Port must be 1–65535');
    }
    s = s.substring(0, colon);
  }
  final parts = s.split('.');
  final octets = parts.map(int.tryParse).toList();
  if (parts.length != 4 ||
      parts.any((p) => !RegExp(r'^\d{1,3}$').hasMatch(p)) ||
      octets.any((o) => o == null || o > 255)) {
    throw const FormatException('Enter an IPv4 address, e.g. 192.168.1.20');
  }
  final [a, b, _, _] = octets.cast<int>();
  final private =
      a == 10 ||
      (a == 172 && b >= 16 && b <= 31) ||
      (a == 192 && b == 168) ||
      (a == 169 && b == 254);
  if (!private) {
    throw const FormatException(
      'Not a LAN address: use the PC’s private IP (10.x, 172.16–31.x, '
      '192.168.x)',
    );
  }
  return 'tcp://${octets.join('.')}:$port';
}
