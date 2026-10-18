import 'package:flutter/material.dart';

import 'theme/app_theme.dart';

/// Live input level while recording: a bar from [minDbfs] to 0 dBFS plus the
/// RMS value. [dbfs] is null until the first frames arrive.
class InputLevelMeter extends StatelessWidget {
  const InputLevelMeter({super.key, required this.dbfs});

  final double? dbfs;

  /// Bottom of the bar; quieter input shows an empty bar.
  static const double minDbfs = -60;

  static const barKey = Key('level-meter-bar');
  static const valueKey = Key('level-meter-value');

  /// `-23.4 dBFS`, or `– dBFS` before the first reading.
  static String format(double? dbfs) =>
      dbfs == null ? '– dBFS' : '${dbfs.toStringAsFixed(1)} dBFS';

  /// Bar fill in 0..1 for [dbfs].
  static double fraction(double? dbfs) =>
      dbfs == null ? 0 : ((dbfs - minDbfs) / -minDbfs).clamp(0.0, 1.0);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final level = dbfs;
    // Near full scale the input is about to clip.
    final color = level != null && level > -3 ? scheme.error : scheme.primary;
    return Semantics(
      label: 'Input level ${format(level)}',
      excludeSemantics: true,
      child: Row(
        key: const Key('level-meter'),
        children: [
          Icon(
            Icons.graphic_eq_rounded,
            color: scheme.onSurfaceVariant,
            size: 20,
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(EvRadius.pill),
              child: LinearProgressIndicator(
                key: barKey,
                value: fraction(level),
                minHeight: 8,
                color: color,
                backgroundColor: scheme.surfaceContainerHighest,
              ),
            ),
          ),
          const SizedBox(width: EvSpace.sm),
          SizedBox(
            width: 84,
            child: Text(
              key: valueKey,
              format(level),
              textAlign: TextAlign.end,
              maxLines: 1,
              style: textTheme.bodySmall?.copyWith(
                color: scheme.onSurfaceVariant,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
