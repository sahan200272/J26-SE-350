import 'package:flutter/material.dart';

/// Echo Vault brand colours and the derived UI palette.
///
/// Brand: deep navy `#0B1220`, electric teal `#22D3C5`, indigo `#6366F1`,
/// light surface/text `#F8FAFC`. The other values are neutral steps between
/// them, chosen for at least 4.5:1 text contrast on the navy background.
abstract final class EvColors {
  // Brand.
  static const navy = Color(0xFF0B1220);
  static const teal = Color(0xFF22D3C5);
  static const indigo = Color(0xFF6366F1);
  static const snow = Color(0xFFF8FAFC);

  // Surfaces (navy, slightly lifted for cards and sheets).
  static const surfaceLow = Color(0xFF111A2B);
  static const surface = Color(0xFF151F33);
  static const surfaceHigh = Color(0xFF1B263D);
  static const surfaceHighest = Color(0xFF223049);

  // Lines.
  static const border = Color(0xFF1F2A40);
  static const borderStrong = Color(0xFF2E3B55);

  // Text.
  static const textMuted = Color(0xFF94A3B8);
  static const textSubtle = Color(0xFF64748B);

  // Status.
  static const recording = Color(0xFFF87171);
  static const recordingDeep = Color(0xFFEF4444);
  static const warning = Color(0xFFFBBF24);
  static const success = Color(0xFF34D399);
}

/// Spacing scale (dp). Use these instead of ad-hoc values.
abstract final class EvSpace {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 24;
  static const double xl = 32;
  static const double xxl = 48;
}

/// Corner radii (dp).
abstract final class EvRadius {
  static const double sm = 10;
  static const double md = 14;
  static const double lg = 20;
  static const double pill = 999;
}

/// Short, restrained motion.
abstract final class EvMotion {
  static const fast = Duration(milliseconds: 160);
  static const medium = Duration(milliseconds: 280);
  static const slow = Duration(milliseconds: 520);
  static const curve = Curves.easeOutCubic;

  /// True when the platform asks for reduced motion.
  static bool reduced(BuildContext context) =>
      MediaQuery.maybeDisableAnimationsOf(context) ?? false;
}

/// The Material zoom page transition (300 ms), or no animation when the
/// platform asks for reduced motion.
class EvPageTransitionsBuilder extends PageTransitionsBuilder {
  const EvPageTransitionsBuilder();

  static const _zoom = ZoomPageTransitionsBuilder();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (EvMotion.reduced(context)) return child;
    return _zoom.buildTransitions(
      route,
      context,
      animation,
      secondaryAnimation,
      child,
    );
  }
}

/// The single (dark) Echo Vault theme.
ThemeData buildEchoVaultTheme() {
  const scheme = ColorScheme(
    brightness: Brightness.dark,
    primary: EvColors.teal,
    onPrimary: EvColors.navy,
    primaryContainer: Color(0xFF0E3B3A),
    onPrimaryContainer: Color(0xFFA7F3EC),
    secondary: EvColors.indigo,
    onSecondary: EvColors.snow,
    secondaryContainer: Color(0xFF23264F),
    onSecondaryContainer: Color(0xFFC7D2FE),
    tertiary: EvColors.warning,
    onTertiary: EvColors.navy,
    tertiaryContainer: Color(0xFF2E2612),
    onTertiaryContainer: Color(0xFFFDE68A),
    error: EvColors.recording,
    onError: EvColors.navy,
    errorContainer: Color(0xFF3A1620),
    onErrorContainer: Color(0xFFFECACA),
    surface: EvColors.navy,
    onSurface: EvColors.snow,
    onSurfaceVariant: EvColors.textMuted,
    surfaceContainerLowest: Color(0xFF080E1A),
    surfaceContainerLow: EvColors.surfaceLow,
    surfaceContainer: EvColors.surface,
    surfaceContainerHigh: EvColors.surfaceHigh,
    surfaceContainerHighest: EvColors.surfaceHighest,
    outline: EvColors.borderStrong,
    outlineVariant: EvColors.border,
    inverseSurface: EvColors.snow,
    onInverseSurface: EvColors.navy,
    inversePrimary: Color(0xFF0F766E),
    shadow: Colors.black,
    scrim: Colors.black,
  );

  final base = ThemeData(
    useMaterial3: true,
    // One page transition everywhere (300 ms), none with reduced motion.
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {TargetPlatform.android: EvPageTransitionsBuilder()},
    ),
    colorScheme: scheme,
    scaffoldBackgroundColor: EvColors.navy,
    canvasColor: EvColors.navy,
    visualDensity: VisualDensity.standard,
  );

  final text = base.textTheme.apply(
    bodyColor: EvColors.snow,
    displayColor: EvColors.snow,
  );

  return base.copyWith(
    textTheme: text.copyWith(
      displayLarge: text.displayLarge?.copyWith(
        fontWeight: FontWeight.w300,
        letterSpacing: -1.5,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
      displayMedium: text.displayMedium?.copyWith(
        fontWeight: FontWeight.w300,
        letterSpacing: -1,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
      headlineMedium: text.headlineMedium?.copyWith(
        fontWeight: FontWeight.w600,
        letterSpacing: -0.5,
      ),
      headlineSmall: text.headlineSmall?.copyWith(
        fontWeight: FontWeight.w600,
        letterSpacing: -0.3,
      ),
      titleLarge: text.titleLarge?.copyWith(fontWeight: FontWeight.w600),
      titleMedium: text.titleMedium?.copyWith(fontWeight: FontWeight.w600),
      titleSmall: text.titleSmall?.copyWith(fontWeight: FontWeight.w600),
      bodyMedium: text.bodyMedium?.copyWith(height: 1.45),
      bodySmall: text.bodySmall?.copyWith(
        color: EvColors.textMuted,
        height: 1.4,
      ),
      labelSmall: text.labelSmall?.copyWith(
        letterSpacing: 1.1,
        fontWeight: FontWeight.w600,
      ),
    ),
    cardTheme: CardThemeData(
      color: EvColors.surfaceLow,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.lg),
        side: const BorderSide(color: EvColors.border),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(64, 52),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(EvRadius.md),
        ),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
        disabledBackgroundColor: EvColors.surfaceHigh,
        disabledForegroundColor: EvColors.textSubtle,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(64, 52),
        foregroundColor: EvColors.snow,
        side: const BorderSide(color: EvColors.borderStrong),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(EvRadius.md),
        ),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
        disabledForegroundColor: EvColors.textSubtle,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: EvColors.teal,
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: EvColors.surfaceLow,
      indicatorColor: EvColors.teal.withValues(alpha: 0.16),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      height: 68,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          size: 24,
          color: states.contains(WidgetState.disabled)
              ? EvColors.textSubtle.withValues(alpha: 0.5)
              : states.contains(WidgetState.selected)
              ? EvColors.teal
              : EvColors.textMuted,
        ),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 12,
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w600
              : FontWeight.w500,
          color: states.contains(WidgetState.disabled)
              ? EvColors.textSubtle.withValues(alpha: 0.5)
              : states.contains(WidgetState.selected)
              ? EvColors.snow
              : EvColors.textMuted,
        ),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      iconColor: EvColors.textMuted,
      contentPadding: EdgeInsets.symmetric(horizontal: EvSpace.md),
    ),
    dividerTheme: const DividerThemeData(
      color: EvColors.border,
      thickness: 1,
      space: 1,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: EvColors.teal,
      linearTrackColor: EvColors.surfaceHigh,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: EvColors.surfaceHighest,
      contentTextStyle: const TextStyle(color: EvColors.snow),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(EvRadius.md),
      ),
    ),
  );
}
