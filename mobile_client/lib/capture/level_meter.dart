import 'dart:math' as math;
import 'dart:typed_data';

/// Lowest level reported, about the 16-bit dynamic range. Digital silence
/// reads as this value instead of −∞.
const double kSilenceFloorDbfs = -96.0;

/// RMS level of the first [count] samples in dBFS, relative to 16-bit full
/// scale (32768): a full-scale square wave is 0 dBFS, a full-scale sine
/// about −3 dBFS. Clamped to [kSilenceFloorDbfs].
double rmsDbfs(Int16List samples, [int? count]) {
  final window = RmsWindow()..add(samples, count);
  return window.takeDbfs() ?? kSilenceFloorDbfs;
}

/// Accumulates samples and reports their RMS level once per read, e.g. once
/// per UI refresh. Pure Dart.
class RmsWindow {
  double _sumOfSquares = 0;
  int _count = 0;

  void add(Int16List samples, [int? count]) {
    final n = count ?? samples.length;
    for (var i = 0; i < n; i++) {
      final s = samples[i].toDouble();
      _sumOfSquares += s * s;
    }
    _count += n;
  }

  /// RMS level in dBFS of everything added since the last call, then resets.
  /// Null if nothing was added.
  double? takeDbfs() {
    if (_count == 0) return null;
    final rms = math.sqrt(_sumOfSquares / _count);
    reset();
    if (rms <= 0) return kSilenceFloorDbfs;
    final db = 20 * math.log(rms / 32768) / math.ln10;
    return math.max(kSilenceFloorDbfs, db);
  }

  void reset() {
    _sumOfSquares = 0;
    _count = 0;
  }
}
