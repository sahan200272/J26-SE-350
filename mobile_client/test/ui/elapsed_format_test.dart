import 'package:echo_vault/ui/elapsed_format.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('formats mm:ss under one hour, h:mm:ss above', () {
    expect(formatElapsed(Duration.zero), '00:00');
    expect(formatElapsed(const Duration(milliseconds: 999)), '00:00');
    expect(formatElapsed(const Duration(seconds: 65)), '01:05');
    expect(formatElapsed(const Duration(minutes: 59, seconds: 59)), '59:59');
    expect(formatElapsed(const Duration(hours: 1)), '1:00:00');
    expect(
      formatElapsed(const Duration(hours: 2, minutes: 3, seconds: 4)),
      '2:03:04',
    );
  });
}
