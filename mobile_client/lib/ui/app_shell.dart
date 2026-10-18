import 'dart:async';

import 'package:flutter/material.dart';

import '../sessions/session_store.dart';
import '../sync/syncthing_client.dart';
import 'assistant_screen.dart';
import 'components.dart';
import 'home_screen.dart';
import 'knowledge_screen.dart';
import 'sessions_screen.dart';
import 'settings_home_screen.dart';
import 'theme/app_theme.dart';

/// Bottom navigation: Home, Sessions, Knowledge, Assistant, Settings.
///
/// Recording happens on its own full-screen page, opened from Home (or the
/// Sessions/Knowledge empty states). That page cannot be left while a
/// session is open, so the recording indicator always stays visible (FR1).
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

enum _Tab { home, sessions, knowledge, assistant, settings }

class _AppShellState extends State<AppShell> {
  _Tab _tab = _Tab.home;
  int _refresh = 0;

  List<_Tab> get _tabs => [
    _Tab.home,
    if (widget.sessions != null) _Tab.sessions,
    _Tab.knowledge,
    _Tab.assistant,
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
      onOpenKnowledge: () => _select(_Tab.knowledge),
      onOpenAssistant: () => _select(_Tab.assistant),
    ),
    _Tab.sessions => SessionsScreen(
      source: widget.sessions!,
      syncthing: widget.syncthing,
      appVersion: widget.appVersion,
      refreshToken: _refresh,
      onStartRecording: _startRecording,
    ),
    _Tab.knowledge => KnowledgeScreen(onStartRecording: _startRecording),
    _Tab.assistant => const AssistantScreen(),
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
    _Tab.knowledge => const NavigationDestination(
      icon: Icon(Icons.hub_outlined),
      selectedIcon: Icon(Icons.hub_rounded),
      label: 'Knowledge',
    ),
    _Tab.assistant => const NavigationDestination(
      icon: Icon(Icons.auto_awesome_outlined),
      selectedIcon: Icon(Icons.auto_awesome_rounded),
      label: 'Assistant',
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
        bottomNavigationBar: DecoratedBox(
          decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: EvColors.border)),
          ),
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

/// Plain navy screen while the first-run check finishes (normally a few
/// milliseconds).
class LaunchPlaceholder extends StatelessWidget {
  const LaunchPlaceholder({super.key});

  @override
  Widget build(BuildContext context) => const ColoredBox(
    color: EvColors.navy,
    child: Center(child: BrandSymbol(size: 112)),
  );
}
