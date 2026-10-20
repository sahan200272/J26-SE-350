import 'package:flutter/material.dart';

import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Shared building blocks of the Ember look (black / deep red, liquid
/// glass). Cards themselves are [LiquidGlass] (ember_theme.dart).

/// Round frosted-glass icon button (app bars, headers). [buttonKey] goes on
/// the underlying [IconButton].
class GlassIconButton extends StatelessWidget {
  const GlassIconButton({
    super.key,
    this.buttonKey,
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final Key? buttonKey;
  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  /// The same look for buttons that are not [IconButton]s (e.g. a
  /// [PopupMenuButton]).
  static final ButtonStyle style = IconButton.styleFrom(
    backgroundColor: EvEmber.glass,
    foregroundColor: Colors.white,
    disabledBackgroundColor: Colors.transparent,
    disabledForegroundColor: EvEmber.textFaint,
    side: const BorderSide(color: EvEmber.glassBorder),
  );

  @override
  Widget build(BuildContext context) {
    return IconButton(
      key: buttonKey,
      tooltip: tooltip,
      onPressed: onPressed,
      style: style,
      icon: Icon(icon, size: 20),
    );
  }
}

/// Compact frosted-glass chip: an icon (or any [leading] widget) and a
/// short label.
class GlassChip extends StatelessWidget {
  const GlassChip({
    super.key,
    required this.label,
    this.icon,
    this.leading,
    this.color = Colors.white,
    this.large = false,
  });

  final String label;
  final IconData? icon;

  /// Used instead of [icon], e.g. the red recording dot.
  final Widget? leading;

  /// Label (and icon) colour.
  final Color color;

  /// A slightly bigger chip for a screen's main status.
  final bool large;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final lead =
        leading ??
        (icon == null
            ? null
            : Icon(
                icon,
                size: large ? 18 : 14,
                color: color == Colors.white ? EvEmber.textSoft : color,
              ));
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: large ? 14 : 10,
        vertical: large ? 7 : 5,
      ),
      decoration: BoxDecoration(
        color: EvEmber.glass,
        borderRadius: BorderRadius.circular(EvRadius.pill),
        border: Border.all(color: EvEmber.glassBorder),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (lead != null) ...[lead, SizedBox(width: large ? 8 : 6)],
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: large
                  ? textTheme.titleSmall?.copyWith(color: color)
                  : textTheme.labelMedium?.copyWith(
                      color: color,
                      fontWeight: FontWeight.w600,
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

/// One-line status on glass: a tinted icon, a title and a short
/// explanation; tappable (with a chevron) when [onTap] is set.
class StatusBanner extends StatelessWidget {
  const StatusBanner({
    super.key,
    required this.icon,
    required this.color,
    required this.title,
    this.subtitle,
    this.onTap,
    this.trailing,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      container: true,
      button: onTap != null,
      child: LiquidGlass(
        radius: 20,
        shadow: false,
        onTap: onTap,
        padding: const EdgeInsets.symmetric(
          horizontal: EvSpace.md,
          vertical: EvSpace.sm,
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color.withValues(alpha: 0.16),
              ),
              child: Icon(icon, size: 18, color: color),
            ),
            const SizedBox(width: EvSpace.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: textTheme.titleSmall?.copyWith(color: Colors.white),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      subtitle!,
                      style: textTheme.bodySmall?.copyWith(
                        color: EvEmber.textSoft,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (trailing != null) ...[
              const SizedBox(width: EvSpace.xs),
              trailing!,
            ] else if (onTap != null)
              const Icon(
                Icons.chevron_right_rounded,
                color: EvEmber.textFaint,
              ),
          ],
        ),
      ),
    );
  }
}

/// A numbered step of a guided flow, on glass. The number turns into a
/// check mark when [done].
class StepCard extends StatelessWidget {
  const StepCard({
    super.key,
    required this.number,
    required this.title,
    required this.child,
    this.done = false,
    this.subtitle,
  });

  final int number;
  final String title;
  final String? subtitle;
  final bool done;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return LiquidGlass(
      radius: 22,
      shadow: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Semantics(
                container: true,
                label: done ? 'Step $number, done' : 'Step $number',
                excludeSemantics: true,
                child: Container(
                  width: 28,
                  height: 28,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: done
                        ? EvColors.success.withValues(alpha: 0.18)
                        : EvEmber.glassStrong,
                    border: Border.all(
                      color: done
                          ? EvColors.success.withValues(alpha: 0.5)
                          : EvEmber.glassBorder,
                    ),
                  ),
                  child: done
                      ? const Icon(
                          Icons.check_rounded,
                          size: 16,
                          color: EvColors.success,
                        )
                      : Text(
                          '$number',
                          style: textTheme.labelLarge?.copyWith(
                            color: Colors.white,
                          ),
                        ),
                ),
              ),
              const SizedBox(width: EvSpace.sm),
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(
                    title,
                    style: textTheme.titleMedium?.copyWith(color: Colors.white),
                  ),
                ),
              ),
            ],
          ),
          if (subtitle != null) ...[
            const SizedBox(height: EvSpace.xs),
            Text(
              subtitle!,
              style: textTheme.bodySmall?.copyWith(color: EvEmber.textSoft),
            ),
          ],
          const SizedBox(height: EvSpace.md),
          child,
        ],
      ),
    );
  }
}
