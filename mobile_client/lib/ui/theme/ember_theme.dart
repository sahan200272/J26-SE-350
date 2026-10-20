import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import 'app_theme.dart';

// Echo Vault design tokens (one set for the whole app)
//
// Colour roles   EvEmber below: surfaces (black, deep, wine, backdropRed),
//                accent (accent, accentSoft; red is an accent, never a fill),
//                text (text, textSoft, textFaint), state (success, warning,
//                danger, dangerText), stop (the Stop button), glass (glass, glassStrong, glassBorder, hairline).
// Type scale     emberTheme's TextTheme (Material 3 roles): display (timer),
//                headline (screen titles), title (cards, sections), body,
//                label (chips, buttons). Numbers use tabular figures.
// Spacing        EvSpace (4-pt grid: 4, 8, 12, 16, 24, 32, 48).
// Radii          EvRadius (10, 14, 20, pill); glass cards 20–24.
// Elevation      Flat. Depth comes from glass levels, not shadows:
//                level 1 = glass (8 % white) for cards and chips,
//                level 2 = glassStrong (12 %) for selected / raised items,
//                edges = glassBorder (15 %), dividers = hairline (10 %).
//                Live blur only outside lists (navigation bar, Home).
// Motion         EvMotion: fast 160 ms, medium 280 ms (pages, sheets),
//                slow 520 ms (backgrounds only), easeOutCubic; nothing
//                moves when reduced motion is on, except real state.

/// The dark black / deep-red look: colours and the "liquid glass" surface
/// used for cards.
abstract final class EvEmber {
  static const black = Color(0xFF070304);
  static const deep = Color(0xFF160606);
  static const wine = Color(0xFF3A0D0D);
  static const red = Color(0xFF8E1B16);
  static const accent = Color(0xFFFF4A3D);
  static const accentSoft = Color(0xFFFF8A7C);

  /// The dark red of the Sessions background.
  static const backdropRed = Color(0xFF420D0D);

  static const text = Colors.white;
  static const textSoft = Color(0xB8FFFFFF); // 72 % white
  // 58 % white: at least 4.5 : 1 (WCAG AA) on glass over the deep red.
  static const textFaint = Color(0x94FFFFFF);
  static const glass = Color(0x14FFFFFF); // 8 % white
  static const glassStrong = Color(0x1FFFFFFF); // 12 % white
  static const glassBorder = Color(0x26FFFFFF); // 15 % white
  static const hairline = Color(0x1AFFFFFF); // 10 % white

  // State colours (the same as the rest of the app).
  static const success = EvColors.success;
  static const warning = EvColors.warning;
  static const danger = EvColors.recording;

  /// Error text on glass (5.6 : 1; [danger] is for icons).
  static const dangerText = Color(0xFFFCA5A5);

  /// The Stop button: white on it is 5.0 : 1 ([accent] is 3.3 : 1).
  static const stop = Color(0xFFD7261C);
}

/// A "liquid glass" surface: a faint white fill that is brighter towards
/// the top-left, a light-catching edge and a soft shadow underneath.
/// Tappable when [onTap] is set.
///
/// [blur] > 0 also blurs what is behind it (a live backdrop blur). It is
/// off by default: over the smooth Ember backgrounds a blur is barely
/// visible but costs a lot while scrolling (it made Sessions lag).
class LiquidGlass extends StatelessWidget {
  const LiquidGlass({
    super.key,
    required this.child,
    this.radius = 24,
    this.padding = const EdgeInsets.all(16),
    this.blur = 0,
    this.onTap,
    this.shadow = true,
  });

  final Widget child;
  final double radius;
  final EdgeInsetsGeometry padding;
  final double blur;
  final VoidCallback? onTap;
  final bool shadow;

  @override
  Widget build(BuildContext context) {
    final shape = BorderRadius.circular(radius);
    Widget content = Padding(padding: padding, child: child);
    if (onTap != null) {
      content = InkWell(
        onTap: onTap,
        borderRadius: shape,
        splashColor: EvEmber.accent.withValues(alpha: 0.16),
        highlightColor: Colors.white.withValues(alpha: 0.04),
        child: content,
      );
    }
    Widget surface = CustomPaint(
      foregroundPainter: _GlassEdgePainter(radius),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: shape,
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0x26FFFFFF), // 15 %
              Color(0x0DFFFFFF), // 5 %
              Color(0x14FFFFFF), // 8 %
            ],
            stops: [0, 0.55, 1],
          ),
        ),
        child: Material(type: MaterialType.transparency, child: content),
      ),
    );
    if (blur > 0) {
      surface = BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: surface,
      );
    }
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: shape,
        boxShadow: shadow
            ? const [
                BoxShadow(
                  color: Color(0x4D000000),
                  blurRadius: 18,
                  offset: Offset(0, 8),
                ),
              ]
            : null,
      ),
      child: ClipRRect(borderRadius: shape, child: surface),
    );
  }
}

/// The glass edge: bright where light would catch it (top-left), fading
/// along the sides, with a faint rim at the bottom-right.
class _GlassEdgePainter extends CustomPainter {
  _GlassEdgePainter(this.radius);

  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final rect = Offset.zero & size;
    final rrect = RRect.fromRectAndRadius(
      rect.deflate(0.5),
      Radius.circular(radius),
    );
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0x73FFFFFF), // 45 %
          Color(0x14FFFFFF), // 8 %
          Color(0x0AFFFFFF), // 4 %
          Color(0x33FFFFFF), // 20 %
        ],
        stops: [0, 0.35, 0.7, 1],
      ).createShader(rect);
    canvas.drawRRect(rrect, paint);
  }

  @override
  bool shouldRepaint(_GlassEdgePainter old) => old.radius != radius;
}

/// Colours the shared components (cards, rows, labels, pills) read from the
/// theme. Screens without the Ember theme get [navy], which is exactly the
/// original look; screens inside [EmberScope] get [ember].
@immutable
class EvPalette extends ThemeExtension<EvPalette> {
  const EvPalette({
    required this.glass,
    required this.card,
    required this.cardBorder,
    required this.muted,
    required this.subtle,
    required this.accent,
    required this.skeleton,
    required this.dialog,
  });

  /// Cards are drawn as [LiquidGlass].
  final bool glass;
  final Color card;
  final Color cardBorder;
  final Color muted;
  final Color subtle;
  final Color accent;
  final Color skeleton;
  final Color dialog;

  static const navy = EvPalette(
    glass: false,
    card: EvColors.surfaceLow,
    cardBorder: EvColors.border,
    muted: EvColors.textMuted,
    subtle: EvColors.textSubtle,
    accent: EvColors.teal,
    skeleton: EvColors.surfaceHigh,
    dialog: EvColors.surface,
  );

  static const ember = EvPalette(
    glass: true,
    card: EvEmber.glass,
    cardBorder: EvEmber.glassBorder,
    muted: EvEmber.textSoft,
    subtle: EvEmber.textFaint,
    accent: EvEmber.accentSoft,
    skeleton: EvEmber.glassStrong,
    dialog: Color(0xFF1E0B0C),
  );

  static EvPalette of(BuildContext context) =>
      Theme.of(context).extension<EvPalette>() ?? navy;

  @override
  EvPalette copyWith({
    bool? glass,
    Color? card,
    Color? cardBorder,
    Color? muted,
    Color? subtle,
    Color? accent,
    Color? skeleton,
    Color? dialog,
  }) => EvPalette(
    glass: glass ?? this.glass,
    card: card ?? this.card,
    cardBorder: cardBorder ?? this.cardBorder,
    muted: muted ?? this.muted,
    subtle: subtle ?? this.subtle,
    accent: accent ?? this.accent,
    skeleton: skeleton ?? this.skeleton,
    dialog: dialog ?? this.dialog,
  );

  @override
  EvPalette lerp(ThemeExtension<EvPalette>? other, double t) {
    if (other is! EvPalette) return this;
    return t < 0.5 ? this : other;
  }
}

/// [base] turned into the black / deep-red Ember theme: white text, coral
/// accent, white primary buttons, glass cards, transparent scaffolds (the
/// page draws [EmberBackdrop] behind them).
ThemeData emberTheme(ThemeData base) {
  final scheme = base.colorScheme.copyWith(
    primary: EvEmber.accent,
    onPrimary: Colors.white,
    primaryContainer: EvEmber.wine,
    onPrimaryContainer: Colors.white,
    secondary: EvEmber.accentSoft,
    onSecondary: EvEmber.black,
    surface: EvEmber.black,
    onSurface: Colors.white,
    onSurfaceVariant: EvEmber.textSoft,
    surfaceTint: Colors.transparent,
    surfaceContainerLowest: const Color(0xFF0C0505),
    surfaceContainerLow: const Color(0xFF140808),
    surfaceContainer: const Color(0xFF1C0B0B),
    surfaceContainerHigh: const Color(0xFF241010),
    surfaceContainerHighest: const Color(0xFF2E1414),
    outline: EvEmber.glassBorder,
    outlineVariant: EvEmber.hairline,
  );
  final text = base.textTheme.apply(
    bodyColor: Colors.white,
    displayColor: Colors.white,
  );
  const buttonText = TextStyle(fontWeight: FontWeight.w600, fontSize: 15);
  return base.copyWith(
    colorScheme: scheme,
    scaffoldBackgroundColor: Colors.transparent,
    canvasColor: const Color(0xFF1C0B0B),
    textTheme: text.copyWith(
      bodySmall: text.bodySmall?.copyWith(color: EvEmber.textSoft),
    ),
    cardTheme: base.cardTheme.copyWith(
      color: EvEmber.glass,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.lg),
        side: const BorderSide(color: EvEmber.glassBorder),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(64, 52),
        backgroundColor: Colors.white,
        foregroundColor: EvEmber.black,
        disabledBackgroundColor: EvEmber.glassStrong,
        disabledForegroundColor: EvEmber.textFaint,
        shape: const StadiumBorder(),
        textStyle: buttonText,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(64, 52),
        foregroundColor: Colors.white,
        disabledForegroundColor: EvEmber.textFaint,
        side: const BorderSide(color: EvEmber.glassBorder),
        shape: const StadiumBorder(),
        textStyle: buttonText,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: EvEmber.accentSoft,
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    dividerTheme: const DividerThemeData(
      color: EvEmber.hairline,
      thickness: 1,
      space: 1,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: EvEmber.accent,
      linearTrackColor: EvEmber.glass,
    ),
    listTileTheme: base.listTileTheme.copyWith(iconColor: EvEmber.textSoft),
    extensions: const [EvPalette.ember],
  );
}

/// Applies [emberTheme] to [child] (and to dialogs opened from it).
class EmberScope extends StatelessWidget {
  const EmberScope({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) =>
      Theme(data: emberTheme(Theme.of(context)), child: child);
}

/// A full page in the Ember look: [EmberBackdrop] behind [child] (usually a
/// [Scaffold], whose background the Ember theme makes transparent).
class EmberPage extends StatelessWidget {
  const EmberPage({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return EmberScope(
      child: Stack(
        fit: StackFit.expand,
        children: [const EmberBackdrop(), child],
      ),
    );
  }
}

/// The Ember background: black in the upper part, deep red in the lower
/// part. The bottom 70 % of the lower half is solid dark red; the top 30 %
/// of the lower half and the bottom 20 % of the upper half (40–65 % of the
/// screen height) blend from red into black. Soft red glows add depth
/// behind the glass cards. Static and cached.
class EmberBackdrop extends StatelessWidget {
  const EmberBackdrop({super.key});

  @override
  Widget build(BuildContext context) {
    return const ExcludeSemantics(
      child: RepaintBoundary(
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    EvEmber.black,
                    EvEmber.black,
                    EvEmber.backdropRed,
                    EvEmber.backdropRed,
                  ],
                  stops: [0, 0.40, 0.65, 1],
                ),
              ),
            ),
            // Glows: light behind the glass, strongest low on the screen.
            _Glow(alignment: Alignment(-0.9, 0.55), size: 1.1, alpha: 0.45),
            _Glow(alignment: Alignment(1.0, 0.95), size: 0.9, alpha: 0.35),
            _Glow(alignment: Alignment(0.7, -0.15), size: 0.6, alpha: 0.14),
          ],
        ),
      ),
    );
  }
}

/// A soft circle of red light ([size] is relative to the screen width).
class _Glow extends StatelessWidget {
  const _Glow({
    required this.alignment,
    required this.size,
    required this.alpha,
  });

  final Alignment alignment;
  final double size;
  final double alpha;

  @override
  Widget build(BuildContext context) {
    final diameter = MediaQuery.sizeOf(context).width * size;
    return Align(
      alignment: alignment,
      child: SizedBox.square(
        dimension: diameter,
        child: DecoratedBox(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: RadialGradient(
              colors: [
                EvEmber.red.withValues(alpha: alpha),
                EvEmber.red.withValues(alpha: 0),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
