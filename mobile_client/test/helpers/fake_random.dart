import 'dart:math';

/// [Random] that always returns [value] from [nextInt].
class FakeRandom implements Random {
  FakeRandom(this.value);

  final int value;
  final List<int> maxes = [];

  @override
  int nextInt(int max) {
    maxes.add(max);
    return value;
  }

  @override
  bool nextBool() => throw UnimplementedError();

  @override
  double nextDouble() => throw UnimplementedError();
}
