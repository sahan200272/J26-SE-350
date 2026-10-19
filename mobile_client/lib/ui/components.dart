import 'package:flutter/material.dart';

import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Logo files (assets/brand/): the "Keyhole Wave" mark (a coral keyhole
/// holding a voice waveform) and the mark with the Sora wordmark. Only
/// dark-UI variants exist: the app has one dark theme.
abstract final class EvBrand {
  /// The standalone mark, for dark backgrounds (512 × 512).
  static const symbol = 'assets/brand/echo-vault-symbol-dark-ui_512.png';

  /// Mark + white "Echo Vault" wordmark, for dark backgrounds (1000 × 289).
  static const horizontal =
      'assets/brand/echo-vault-horizontal-dark-bg_1000.png';

  /// Width / height of [horizontal].
  static const horizontalAspect = 1000 / 289;

  static const tagline = 'Your voice. Your knowledge. Your privacy.';
}

/// The Echo Vault symbol at [size] (square), proportions unchanged.
class BrandSymbol extends StatelessWidget {
  const BrandSymbol({super.key, this.size = 28, this.semanticLabel});

  final double size;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final dpr = MediaQuery.maybeDevicePixelRatioOf(context) ?? 2;
    return Image.asset(
      EvBrand.symbol,
      width: size,
      height: size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      cacheWidth: (size * dpr).ceil().clamp(16, 512),
      semanticLabel: semanticLabel,
      excludeFromSemantics: semanticLabel == null,
    );
  }
}

/// The horizontal Echo Vault logo at [height], proportions unchanged.
class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.height = 40});

  final double height;

  @override
  Widget build(BuildContext context) {
    final dpr = MediaQuery.maybeDevicePixelRatioOf(context) ?? 2;
    final width = height * EvBrand.horizontalAspect;
    return Image.asset(
      EvBrand.horizontal,
      height: height,
      width: width,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      cacheWidth: (width * dpr).ceil().clamp(64, 1000),
      semanticLabel: 'Echo Vault',
    );
  }
}

/// App bar title: compact symbol + product name.
class BrandTitle extends StatelessWidget {
  const BrandTitle({super.key, this.title = 'Echo Vault'});

  final String title;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const BrandSymbol(size: 26),
        const SizedBox(width: EvSpace.xs + 2),
        Flexible(
          child: Text(
            title,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(letterSpacing: -0.2),
          ),
        ),
      ],
    );
  }
}

/// A rounded, bordered surface. Tappable when [onTap] is set.
class EvCard extends StatelessWidget {
  const EvCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(EvSpace.md),
    this.onTap,
    this.color,
    this.borderColor,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;
  final Color? color;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final palette = EvPalette.of(context);
    if (palette.glass && color == null) {
      return LiquidGlass(
        radius: EvRadius.lg,
        padding: padding,
        onTap: onTap,
        shadow: false,
        child: child,
      );
    }
    final radius = BorderRadius.circular(EvRadius.lg);
    return Material(
      color: color ?? palette.card,
      shape: RoundedRectangleBorder(
        borderRadius: radius,
        side: BorderSide(color: borderColor ?? palette.cardBorder),
      ),
      clipBehavior: Clip.antiAlias,
      child: onTap == null
          ? Padding(padding: padding, child: child)
          : InkWell(
              onTap: onTap,
              child: Padding(padding: padding, child: child),
            ),
    );
  }
}

/// Small uppercase heading above a group of cards.
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key, this.trailing});

  final String text;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.xxs,
        EvSpace.lg,
        EvSpace.xxs,
        EvSpace.xs,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              text.toUpperCase(),
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: EvPalette.of(context).muted,
              ),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

enum PillTone { neutral, accent, positive, warning, danger, indigo }

/// Compact status chip: icon + short label.
class StatusPill extends StatelessWidget {
  const StatusPill({
    super.key,
    required this.label,
    this.icon,
    this.tone = PillTone.neutral,
  });

  final String label;
  final IconData? icon;
  final PillTone tone;

  Color _color(EvPalette palette) => switch (tone) {
    PillTone.neutral => palette.muted,
    PillTone.accent => palette.accent,
    PillTone.positive => EvColors.success,
    PillTone.warning => EvColors.warning,
    PillTone.danger => EvColors.recording,
    PillTone.indigo => const Color(0xFFA5B4FC),
  };

  @override
  Widget build(BuildContext context) {
    final color = _color(EvPalette.of(context));
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(EvRadius.pill),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 6),
          ],
          Flexible(
            child: Text(
              label,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
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

/// Tinted circle holding an icon, used as a leading visual.
class IconBadge extends StatelessWidget {
  const IconBadge(this.icon, {super.key, this.color, this.size = 40});

  final IconData icon;

  /// Defaults to the theme's accent (teal, or coral in the Ember look).
  final Color? color;
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = this.color ?? EvPalette.of(context).accent;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(size * 0.32),
      ),
      child: Icon(icon, color: color, size: size * 0.5),
    );
  }
}

/// One row inside a card: leading badge, title, optional subtitle and
/// trailing widget. Tappable when [onTap] is set (shows a chevron).
class InfoRow extends StatelessWidget {
  const InfoRow({
    super.key,
    required this.icon,
    required this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
    this.iconColor,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;

  /// Defaults to the theme's accent.
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final palette = EvPalette.of(context);
    final row = Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: EvSpace.md,
        vertical: EvSpace.sm,
      ),
      child: Row(
        children: [
          IconBadge(icon, color: iconColor ?? palette.accent, size: 36),
          const SizedBox(width: EvSpace.sm + 2),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: textTheme.titleSmall),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(subtitle!, style: textTheme.bodySmall),
                ],
              ],
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: EvSpace.xs),
            trailing!,
          ] else if (onTap != null)
            Icon(Icons.chevron_right, color: palette.subtle),
        ],
      ),
    );
    return onTap == null ? row : InkWell(onTap: onTap, child: row);
  }
}

/// Card holding [InfoRow]s separated by hairlines.
class GroupCard extends StatelessWidget {
  const GroupCard({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return EvCard(
      padding: EdgeInsets.zero,
      child: Column(
        children: [
          for (final (i, child) in children.indexed) ...[
            if (i > 0) const Divider(indent: 66),
            child,
          ],
        ],
      ),
    );
  }
}

/// Centered icon, title, message and optional action, for empty or
/// unavailable content.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
    this.action,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final muted = EvPalette.of(context).muted;
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: EvSpace.lg,
        vertical: EvSpace.xl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconBadge(icon, size: 56, color: muted),
          const SizedBox(height: EvSpace.md),
          Text(title, style: textTheme.titleMedium, textAlign: TextAlign.center),
          const SizedBox(height: EvSpace.xs),
          Text(
            message,
            style: textTheme.bodyMedium?.copyWith(color: muted),
            textAlign: TextAlign.center,
          ),
          if (action != null) ...[
            const SizedBox(height: EvSpace.lg),
            action!,
          ],
        ],
      ),
    );
  }
}

/// Inline notice: tinted card with an icon, title and text.
class NoticeCard extends StatelessWidget {
  const NoticeCard({
    super.key,
    required this.icon,
    required this.message,
    this.title,
    this.tone = PillTone.neutral,
  });

  final IconData icon;
  final String? title;
  final String message;
  final PillTone tone;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final palette = EvPalette.of(context);
    final color = switch (tone) {
      PillTone.danger => EvColors.recording,
      PillTone.warning => EvColors.warning,
      PillTone.accent || PillTone.positive => palette.accent,
      PillTone.indigo => const Color(0xFFA5B4FC),
      PillTone.neutral => palette.muted,
    };
    return Container(
      padding: const EdgeInsets.all(EvSpace.md),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(EvRadius.md),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null) ...[
                  Text(
                    title!,
                    style: textTheme.titleSmall?.copyWith(color: color),
                  ),
                  const SizedBox(height: 2),
                ],
                Text(
                  message,
                  style: textTheme.bodyMedium?.copyWith(color: EvColors.snow),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Section heading with an optional text action, e.g. "See all".
class SectionTitle extends StatelessWidget {
  const SectionTitle(
    this.text, {
    super.key,
    this.actionLabel,
    this.onAction,
  });

  final String text;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.xxs,
        EvSpace.lg,
        0,
        EvSpace.xs,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(text, style: Theme.of(context).textTheme.titleMedium),
          ),
          if (actionLabel != null && onAction != null)
            TextButton(onPressed: onAction, child: Text(actionLabel!)),
        ],
      ),
    );
  }
}

/// Large page title with an optional muted subtitle and trailing widget,
/// used at the top of the main tabs (Sessions, Settings).
class PageHeader extends StatelessWidget {
  const PageHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.trailing,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        EvSpace.xxs,
        EvSpace.md,
        EvSpace.xxs,
        EvSpace.xs,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  header: true,
                  child: Text(title, style: textTheme.headlineMedium),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: EvSpace.xxs),
                  Text(
                    subtitle!,
                    style: textTheme.bodyMedium?.copyWith(
                      color: EvPalette.of(context).muted,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: EvSpace.sm),
            trailing!,
          ],
        ],
      ),
    );
  }
}

/// Placeholder block shown while content loads.
class SkeletonCard extends StatelessWidget {
  const SkeletonCard({super.key, this.height = 84});

  final double height;

  @override
  Widget build(BuildContext context) {
    final fill = EvPalette.of(context).skeleton;
    Widget bar(double width, double h) => Container(
      width: width,
      height: h,
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(EvRadius.sm),
      ),
    );
    return ExcludeSemantics(
      child: EvCard(
        child: SizedBox(
          height: height - 2 * EvSpace.md,
          child: Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: fill,
                  borderRadius: BorderRadius.circular(13),
                ),
              ),
              const SizedBox(width: EvSpace.sm),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    bar(140, 12),
                    const SizedBox(height: EvSpace.xs),
                    bar(90, 10),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
