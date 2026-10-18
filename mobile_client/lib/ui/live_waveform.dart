import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'theme/app_theme.dart';

/// Rolling bar waveform of recent input levels (each 0..1, oldest first).
/// Drawn from the real microphone level; when [levels] is empty or
/// [active] is false it shows a calm flat line.
class LiveWaveform extends StatelessWidget {
  const LiveWaveform({
    super.key,
    required this.levels,
    this.active = true,
    this.color = EvColors.teal,
    this.height = 72,
    this.bars = 40,
  });

  final List<double> levels;
  final bool active;
  final Color color;
  final double height;

  /// Number of bars drawn; the newest [levels] fill from the right.
  final int bars;

  static const waveKey = Key('live-waveform');

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: SizedBox(
        key: waveKey,
        height: height,
        width: double.infinity,
        child: CustomPaint(
          painter: _WaveformPainter(
            levels: levels,
            active: active,
            color: color,
            bars: bars,
          ),
        ),
      ),
    );
  }
}

class _WaveformPainter extends CustomPainter {
  _WaveformPainter({
    required this.levels,
    required this.active,
    required this.color,
    required this.bars,
  });

  final List<double> levels;
  final bool active;
  final Color color;
  final int bars;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || bars <= 0) return;
    final slot = size.width / bars;
    final barWidth = math.max(2.0, slot * 0.55);
    final mid = size.height / 2;
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = barWidth;
    final start = math.max(0, levels.length - bars);
    final visible = levels.sublist(start);
    final offset = bars - visible.length;
    for (var i = 0; i < bars; i++) {
      final j = i - offset;
      final level = (active && j >= 0) ? visible[j].clamp(0.0, 1.0) : 0.0;
      // A soft curve so quiet speech is still visible.
      final shaped = math.pow(level, 0.8).toDouble();
      final half = math.max(barWidth / 2, shaped * (size.height / 2 - 2));
      final x = slot * i + slot / 2;
      final age = bars <= 1 ? 1.0 : i / (bars - 1);
      paint.color = (active && j >= 0 ? color : EvColors.borderStrong)
          .withValues(alpha: active ? 0.35 + 0.65 * age : 0.8);
      canvas.drawLine(Offset(x, mid - half), Offset(x, mid + half), paint);
    }
  }

  @override
  bool shouldRepaint(_WaveformPainter old) =>
      old.levels != levels ||
      old.levels.length != levels.length ||
      old.active != active ||
      old.color != color;
}
