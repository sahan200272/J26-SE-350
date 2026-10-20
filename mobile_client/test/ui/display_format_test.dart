import 'package:echo_vault/ui/display_format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final now = DateTime(2026, 10, 20, 9, 30);

  group('formatWhen', () {
    test('today and yesterday', () {
      expect(formatWhen(DateTime(2026, 10, 20, 14, 5), now), 'Today, 14:05');
      expect(
        formatWhen(DateTime(2026, 10, 19, 23, 59), now),
        'Yesterday, 23:59',
      );
    });

    test('earlier this year shows the weekday', () {
      expect(
        formatWhen(DateTime(2026, 10, 18, 14, 5), now),
        'Sun 18 Oct, 14:05',
      );
    });

    test('another year shows the year', () {
      expect(
        formatWhen(DateTime(2025, 10, 18, 8, 0), now),
        '18 Oct 2025, 08:00',
      );
    });
  });

  test('formatLength uses the recording timer style', () {
    expect(formatLength(0), '00:00');
    expect(formatLength(65400), '01:05');
    expect(formatLength(3727000), '1:02:07');
  });
}
