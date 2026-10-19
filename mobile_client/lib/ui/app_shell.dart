import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'components.dart';
import 'home_screen.dart';
import 'sessions_screen.dart';
import 'settings_home_screen.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Bottom navigation: Home, Sessions, Settings. The app focuses on
/// recording; there are no Knowledge or Assistant screens.
///
/// Recording happens on its own full-screen page, opened from Home (or the
/// Sessions empty state). That page cannot be left while a session is open,
/// so the recording indicator always stays visible (FR1).
class AppShell extends StatefulWidget {
  const AppShell({
    super.key,
    this.recordingBuilder,
    this.sessions,
    this.syncthing,
    this.appVersion,
    this.onShowWelcome,
  });

  /// Builds the recording page; recording is unavailable when null.
  final WidgetBuilder? recordingBuilder;

  /// Recordings on this phone; the Sessions tab is hidden when null.
  final SessionSource? sessions;
  final SyncthingClient? syncthing;
  final Future<String>? appVersion;
  final VoidCallback? onShowWelcome;

  static const navKey = Key('app-navigation');

  @override
  State<AppShell> createState() => _AppShellState();
}

enum _Tab { home, sessions, settings }

class _AppShellState extends State<AppShell> {
  _Tab _tab = _Tab.home;
  int _refresh = 0;

  List<_Tab> get _tabs => [
    _Tab.home,
    if (widget.sessions != null) _Tab.sessions,
    _Tab.settings,
  ];

  VoidCallback? get _startRecording {
    final builder = widget.recordingBuilder;
    if (builder == null) return null;
    return () => unawaited(
      Navigator.of(context)
          .push(
            MaterialPageRoute<void>(fullscreenDialog: true, builder: builder),
          )
          // A recording may have been saved: refresh the lists.
          .then((_) {
            if (mounted) setState(() => _refresh++);
          }),
    );
  }

  /// Every tab now has the dark black / deep-red look, with its background
  /// running behind the floating bar.
  bool get _immersive => true;

  void _select(_Tab tab) {
    if (tab == _tab) return;
    setState(() {
      _tab = tab;
      if (tab == _Tab.sessions || tab == _Tab.home) _refresh++;
    });
  }

  Widget _page(_Tab tab) => switch (tab) {
    _Tab.home => HomeScreen(
      sessions: widget.sessions,
      syncthing: widget.syncthing,
      refreshToken: _refresh,
      onStartRecording: _startRecording,
      onOpenSessions: widget.sessions == null
          ? null
          : () => _select(_Tab.sessions),
    ),
    _Tab.sessions => SessionsScreen(
      source: widget.sessions!,
      syncthing: widget.syncthing,
      appVersion: widget.appVersion,
      refreshToken: _refresh,
      onStartRecording: _startRecording,
    ),
    _Tab.settings => SettingsHomeScreen(
      syncthing: widget.syncthing,
      appVersion: widget.appVersion,
      onShowWelcome: widget.onShowWelcome,
    ),
  };

  static NavigationDestination _destination(_Tab tab) => switch (tab) {
    _Tab.home => const NavigationDestination(
      icon: Icon(Icons.home_outlined),
      selectedIcon: Icon(Icons.home_rounded),
      label: 'Home',
    ),
    _Tab.sessions => const NavigationDestination(
      icon: Icon(Icons.graphic_eq_rounded),
      selectedIcon: Icon(Icons.graphic_eq_rounded),
      label: 'Sessions',
    ),
    _Tab.settings => const NavigationDestination(
      icon: Icon(Icons.settings_outlined),
      selectedIcon: Icon(Icons.settings_rounded),
      label: 'Settings',
    ),
  };

  @override
  Widget build(BuildContext context) {
    final tabs = _tabs;
    final index = tabs.indexOf(_tab);
    final fade = EvMotion.reduced(context) ? Duration.zero : EvMotion.fast;
    return PopScope(
      // Back from another tab returns Home before leaving the app.
      canPop: _tab == _Tab.home,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) setState(() => _tab = _Tab.home);
      },
      child: Scaffold(
        // Home's and Sessions' backgrounds run behind the floating bar.
        extendBody: _immersive,
        body: IndexedStack(
          index: index,
          children: [
            for (final tab in tabs)
              AnimatedOpacity(
                opacity: tab == _tab ? 1 : 0,
                duration: fade,
                child: _page(tab),
              ),
          ],
        ),
        bottomNavigationBar: _FloatingNavBar(
          immersive: _immersive,
          child: NavigationBar(
            key: AppShell.navKey,
            selectedIndex: index,
            onDestinationSelected: (i) => _select(tabs[i]),
            destinations: [for (final tab in tabs) _destination(tab)],
          ),
        ),
      ),
    );
  }
}

/// The navigation bar as a rounded, floating pill above the system
/// navigation area. The bar sits below the page content (not over it), so
/// nothing is hidden behind it.
class _FloatingNavBar extends StatelessWidget {
  const _FloatingNavBar({required this.child, this.immersive = false});

  final Widget child;

  /// A dark frosted-glass bar over the background, with neutral (white)
  /// selection (the teal style is kept for [immersive] false).
  final bool immersive;

  @override
  Widget build(BuildContext context) {
    final base = NavigationBarTheme.of(context);
    final theme = immersive
        ? base.copyWith(
            height: 64,
            backgroundColor: const Color(0x8C120607),
            indicatorShape: const StadiumBorder(),
            indicatorColor: Colors.white.withValues(alpha: 0.14),
            iconTheme: WidgetStateProperty.resolveWith(
              (states) => IconThemeData(
                size: 24,
                color: states.contains(WidgetState.selected)
                    ? Colors.white
                    : Colors.white.withValues(alpha: 0.6),
              ),
            ),
            labelTextStyle: WidgetStateProperty.resolveWith(
              (states) => TextStyle(
                fontSize: 12,
                fontWeight: states.contains(WidgetState.selected)
                    ? FontWeight.w600
                    : FontWeight.w500,
                color: states.contains(WidgetState.selected)
                    ? Colors.white
                    : Colors.white.withValues(alpha: 0.6),
              ),
            ),
          )
        : base.copyWith(
            height: 64,
            backgroundColor: EvColors.surface,
            indicatorShape: const StadiumBorder(),
          );
    final borderColor = immersive
        ? Colors.white.withValues(alpha: 0.10)
        : EvColors.border;
    Widget bar = MediaQuery.removePadding(
      // The SafeArea below already keeps clear of the system bar.
      context: context,
      removeBottom: true,
      child: NavigationBarTheme(data: theme, child: child),
    );
    if (immersive) {
      bar = BackdropFilter(
        filter: ui.ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: bar,
      );
    }
    return ColoredBox(
      color: immersive ? Colors.transparent : EvColors.navy,
      child: SafeArea(
        top: false,
        minimum: const EdgeInsets.only(bottom: EvSpace.xs),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.lg,
            EvSpace.xxs,
            EvSpace.lg,
            EvSpace.xs,
          ),
          child: DecoratedBox(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(EvRadius.pill),
              border: Border.all(color: borderColor),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x66000000),
                  blurRadius: 24,
                  offset: Offset(0, 8),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(EvRadius.pill),
              child: bar,
            ),
          ),
        ),
      ),
    );
  }
}

/// Plain black screen while the first-run check finishes (normally a few
/// milliseconds).
class LaunchPlaceholder extends StatelessWidget {
  const LaunchPlaceholder({super.key});

  @override
  Widget build(BuildContext context) => const ColoredBox(
    color: EvEmber.black,
    child: Center(child: BrandSymbol(size: 112)),
  );
}
