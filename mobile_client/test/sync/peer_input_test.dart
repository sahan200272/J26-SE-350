import 'package:echo_vault/sync/peer_input.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_syncthing_client.dart';

void main() {
  group('normalizeDeviceId', () {
    // Real IDs: this phone's (A5 device run), one from `syncthing generate`
    // v2.1.6 on the PC, and the example in Syncthing's REST docs.
    const valid = [
      phoneId,
      pcId,
      'P56IOI7-MZJNU2Y-IQGDREY-DM2MGTI-MGL3BXN-PQ6W5BM-TBBZ4TJ-XZWICQ2',
    ];

    test('accepts valid IDs unchanged', () {
      for (final id in valid) {
        expect(normalizeDeviceId(id), id);
      }
    });

    test('accepts lower case, no dashes, spaces and surrounding blanks', () {
      final compact = phoneId.replaceAll('-', '').toLowerCase();
      expect(normalizeDeviceId(compact), phoneId);
      expect(normalizeDeviceId('  ${phoneId.replaceAll('-', ' ')}\n'), phoneId);
    });

    test('corrects the typos Syncthing corrects: 0→O, 1→I, 8→B', () {
      // pcId contains O, I and B.
      final typed = pcId
          .replaceAll('O', '0')
          .replaceAll('I', '1')
          .replaceAll('B', '8');
      expect(typed, isNot(pcId));
      expect(normalizeDeviceId(typed), pcId);
    });

    test('accepts the old 52-character form and adds check characters', () {
      final compact = phoneId.replaceAll('-', '');
      final old = [
        for (var g = 0; g < 4; g++) compact.substring(g * 14, g * 14 + 13),
      ].join();
      expect(old, hasLength(52));
      expect(normalizeDeviceId(old), phoneId);
    });

    test('rejects a typo through the check character', () {
      final wrong = '${phoneId.substring(0, phoneId.length - 1)}M';
      expect(
        () => normalizeDeviceId(wrong),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains('typo'),
          ),
        ),
      );
      // A changed data character is caught too.
      final swapped = phoneId.replaceFirst('KBPELAQ', 'KBPELAR');
      expect(() => normalizeDeviceId(swapped), throwsFormatException);
    });

    test('rejects wrong lengths, other characters and empty input', () {
      expect(() => normalizeDeviceId(''), throwsFormatException);
      expect(
        () => normalizeDeviceId(phoneId.substring(0, 40)),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains('characters'),
          ),
        ),
      );
      expect(
        () => normalizeDeviceId(phoneId.replaceFirst('K', '9')),
        throwsA(
          isA<FormatException>().having(
            (e) => e.message,
            'message',
            contains('9'),
          ),
        ),
      );
    });
  });

  group('lanAddress', () {
    test('builds tcp://<ip>:22000 from an IP, IP:port or a full address', () {
      expect(lanAddress('192.168.1.20'), 'tcp://192.168.1.20:22000');
      expect(lanAddress(' 192.168.1.20 '), 'tcp://192.168.1.20:22000');
      expect(lanAddress('192.168.1.20:22001'), 'tcp://192.168.1.20:22001');
      expect(lanAddress('tcp://10.0.0.5:22000'), 'tcp://10.0.0.5:22000');
      expect(lanAddress('TCP://10.0.0.5'), 'tcp://10.0.0.5:22000');
    });

    test('accepts private and link-local IPv4 ranges only', () {
      for (final ip in [
        '10.0.0.1',
        '10.255.255.254',
        '172.16.0.1',
        '172.31.255.1',
        '192.168.0.1',
        '169.254.10.2',
      ]) {
        expect(lanAddress(ip), 'tcp://$ip:22000', reason: ip);
      }
      for (final ip in [
        '8.8.8.8',
        '172.15.0.1',
        '172.32.0.1',
        '192.169.0.1',
        '100.64.0.1',
        '127.0.0.1',
        '0.0.0.0',
      ]) {
        expect(
          () => lanAddress(ip),
          throwsA(
            isA<FormatException>().having(
              (e) => e.message,
              'message',
              contains('LAN'),
            ),
          ),
          reason: ip,
        );
      }
    });

    test('rejects host names, malformed addresses and bad ports', () {
      for (final input in [
        '',
        'my-pc.local',
        '192.168.1',
        '192.168.1.256',
        '192.168.1.-1',
        '192.168.1.20.5',
        '192.168.1.20:0',
        '192.168.1.20:65536',
        '192.168.1.20:abc',
        'udp://192.168.1.20',
      ]) {
        expect(() => lanAddress(input), throwsFormatException, reason: input);
      }
    });
  });
}
