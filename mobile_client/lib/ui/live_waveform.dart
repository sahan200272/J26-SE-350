import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'theme/ember_theme.dart';

/// Flowing "silk" wave of recent input levels (each 0..1, oldest first).
///
/// The shape follows the real microphone level: [levels] set the height of
/// the wave along its length (oldest on the left, newest on the right). Only
/// the gentle drift of the ribbons is animated, and only while [active]
/// (and [animate], and the system does not ask for reduced motion). When
/// [levels] is empty or [active] is false it shows a calm glowing line.
class LiveWaveform extends StatefulWidget {
  const LiveWaveform({
    super.key,
    required this.levels,
    this.active = true,
    this.color = EvEmber.accentSoft,
    this.height = 72,
    this.bars = 40,
    this.animate = true,
  });

  final List<double> levels;
  final bool active;

  /// Tint of the ribbons (white at the core, [color] towards the edges).
  final Color color;
  final double height;

  /// How many of the newest [levels] span the width.
  final int bars;

  /// Let the ribbons drift; off for small static previews.
  final bool animate;

  static const waveKey = Key('live-waveform');

  @override
  State<LiveWaveform> createState() => _LiveWaveformState();
}

class _LiveWaveformState extends State<LiveWaveform>
    with SingleTickerProviderStateMixin {
  late final AnimationController _drift = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 8),
  );

  bool get _shouldDrift =>
      widget.active &&
      widget.animate &&
      !(MediaQuery.maybeDisableAnimationsOf(context) ?? false);

  void _syncDrift() {
    if (_shouldDrift) {
      if (!_drift.isAnimating) _drift.repeat();
    } else if (_drift.isAnimating) {
      _drift.stop();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncDrift();
  }

  @override
  void didUpdateWidget(LiveWaveform old) {
    super.didUpdateWidget(old);
    _syncDrift();
  }

  @override
  void dispose() {
    _drift.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ExcludeSemantics(
      child: RepaintBoundary(
        child: SizedBox(
          key: LiveWaveform.waveKey,
          height: widget.height,
          width: double.infinity,
          child: CustomPaint(
            painter: _SilkPainter(
              levels: widget.levels,
              active: widget.active,
              color: widget.color,
              bars: widget.bars,
              drift: _drift,
            ),
          ),
        ),
      ),
    );
  }
}

/// One ribbon: how tall (share of the envelope), how wavy, how fast.
class _Ribbon {
  const _Ribbon(this.scale, this.cycles, this.speed, this.phase, this.alpha);

  final double scale;
  final double cycles;
  final double speed;
  final double phase;
  final double alpha;
}

class _SilkPainter extends CustomPainter {
  _SilkPainter({
    required this.levels,
    required this.active,
    required this.color,
    required this.bars,
    required this.drift,
  }) : super(repaint: drift);

  final List<double> levels;
  final bool active;
  final Color color;
  final int bars;
  final Animation<double> drift;

  static const _ribbons = [
    _Ribbon(1.00, 1.6, 1, 0.0, 0.22),
    _Ribbon(0.85, 2.3, -1, 1.7, 0.26),
    _Ribbon(0.70, 3.1, 2, 3.1, 0.30),
    _Ribbon(0.55, 1.9, -2, 4.4, 0.34),
    _Ribbon(0.38, 2.7, 3, 5.6, 0.42),
  ];

  /// Real level at [t] (0 = oldest shown, 1 = newest), interpolated.
  double _level(List<double> visible, double t) {
    if (visible.isEmpty) return 0;
    if (visible.length == 1) return visible.first;
    final x = t * (visible.length - 1);
    final i = x.floor().clamp(0, visible.length - 2);
    final f = x - i;
    return visible[i] * (1 - f) + visible[i + 1] * f;
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;
    final w = size.width;
    final mid = size.height / 2;
    final half = size.height / 2 - 2;
    final start = math.max(0, levels.length - bars);
    final visible = active ? levels.sublist(start) : const <double>[];
    final time = drift.value * 2 * math.pi;
    const step = 4.0;
    final n = (w / step).ceil();

    // Envelope: real level (softly shaped so quiet speech still shows),
    // tapered to nothing at both ends; a thin line when there is no level.
    final envelope = List<double>.generate(n + 1, (k) {
      final t = k / n;
      final taper = math.pow(math.sin(math.pi * t), 1.2).toDouble();
      final level =
          math.pow(_level(visible, t).clamp(0.0, 1.0), 0.75).toDouble();
      return taper * (0.04 + 0.96 * level);
    });

    final shader = LinearGradient(
      colors: [
        color.withValues(alpha: 0),
        Colors.white,
        color,
        color.withValues(alpha: 0),
      ],
      stops: const [0, 0.45, 0.75, 1],
    ).createShader(Offset.zero & size);

    for (final r in _ribbons) {
      final top = Path();
      final bottom = <Offset>[];
      for (var k = 0; k <= n; k++) {
        final x = math.min(w, k * step);
        final t = x / w;
        final a = envelope[k] * half * r.scale;
        final wave = math.sin(2 * math.pi * r.cycles * t + r.phase + r.speed * time);
        final wave2 = math.sin(
          2 * math.pi * (r.cycles * 0.7) * t - r.phase + r.speed * time * 0.8,
        );
        final up = mid - a * (0.55 + 0.45 * wave);
        final down = mid + a * (0.35 + 0.4 * wave2);
        if (k == 0) {
          top.moveTo(x, up);
        } else {
          top.lineTo(x, up);
        }
        bottom.add(Offset(x, down));
      }
      for (final p in bottom.reversed) {
        top.lineTo(p.dx, p.dy);
      }
      top.close();
      final paint = Paint()
        ..shader = shader
        ..blendMode = BlendMode.plus
        ..color = Colors.white.withValues(alpha: active ? r.alpha : r.alpha * 0.5);
      canvas.drawPath(top, paint);
    }

    // The bright seam through the middle, with a soft glow.
    final seam = Path();
    for (var k = 0; k <= n; k++) {
      final x = math.min(w, k * step);
      final t = x / w;
      final y = mid +
          envelope[k] *
              half *
              0.12 *
              math.sin(2 * math.pi * 2.2 * t + time * 1.5);
      if (k == 0) {
        seam.moveTo(x, y);
      } else {
        seam.lineTo(x, y);
      }
    }
    canvas.drawPath(
      seam,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 6
        ..shader = shader
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6)
        ..color = Colors.white.withValues(alpha: active ? 0.7 : 0.35),
    );
    canvas.drawPath(
      seam,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4
        ..shader = shader
        ..color = Colors.white.withValues(alpha: active ? 0.95 : 0.5),
    );
  }

  @override
  bool shouldRepaint(_SilkPainter old) =>
      old.levels != levels ||
      old.levels.length != levels.length ||
      old.active != active ||
      old.color != color ||
      old.bars != bars;
}
