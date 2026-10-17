import 'dart:math';
import 'dart:typed_data';

import 'package:echo_vault/capture/level_meter.dart';
import 'package:flutter_test/flutter_test.dart';

Int16List constant(int n, int value) => Int16List(n)..fillRange(0, n, value);

void main() {
  test('RMS in dBFS relative to 16-bit full scale', () {
    // Constant 3277 ≈ 0.1 × full scale → −20 dBFS.
    expect(rmsDbfs(constant(512, 3277)), closeTo(-20.0, 0.01));
    expect(rmsDbfs(constant(512, 16384)), closeTo(-6.02, 0.01));
    expect(rmsDbfs(constant(512, -32768)), closeTo(0.0, 1e-9));

    // Full-scale square wave ≈ 0 dBFS; full-scale sine ≈ −3.01 dBFS.
    final square = Int16List.fromList([
      for (var i = 0; i < 512; i++) i.isEven ? 32767 : -32768,
    ]);
    expect(rmsDbfs(square), closeTo(0.0, 0.001));
    final sine = Int16List.fromList([
      for (var i = 0; i < 16000; i++)
        (32767 * sin(2 * pi * 440 * i / 16000)).round(),
    ]);
    expect(rmsDbfs(sine), closeTo(-3.01, 0.01));
  });

  test('silence and empty input read as the floor, never -infinity', () {
    expect(rmsDbfs(Int16List(512)), kSilenceFloorDbfs);
    expect(rmsDbfs(Int16List(0)), kSilenceFloorDbfs);
    // 1 LSB in 1e6 samples is far below the floor.
    final tiny = Int16List(1000000)..[0] = 1;
    expect(rmsDbfs(tiny), kSilenceFloorDbfs);
  });

  test('only the first count samples are measured (padded frames)', () {
    final frame = Int16List(512)..fillRange(0, 100, 3277);
    expect(rmsDbfs(frame, 100), closeTo(-20.0, 0.01));
    expect(rmsDbfs(frame), lessThan(-26));
  });

  test('RmsWindow averages everything since the last read, then resets', () {
    final w = RmsWindow();
    expect(w.takeDbfs(), isNull);
    w
      ..add(constant(512, 3277))
      ..add(constant(512, 3277));
    expect(w.takeDbfs(), closeTo(-20.0, 0.01));
    expect(w.takeDbfs(), isNull);

    // Equal energy split: mean square of (16384² and 0) halves → −9.03 dB.
    w
      ..add(constant(512, 16384))
      ..add(constant(512, 0));
    expect(w.takeDbfs(), closeTo(-9.03, 0.01));
  });
}
