import 'dart:async';

import 'package:flutter/material.dart';

import '../platform/app_channel.dart';
import '../sync/syncthing_client.dart';
import 'about_screen.dart';
import 'components.dart';
import 'processing_privacy_screen.dart';
import 'settings_screen.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Settings: the PC connection, privacy, and app information, in plain
/// language. Implementation details live in Processing & privacy.
class SettingsHomeScreen extends StatelessWidget {
  const SettingsHomeScreen({
    super.key,
    this.syncthing,
    this.appVersion,
    this.onShowWelcome,
    this.openSettings = openAppSettings,
  });

  final SyncthingClient? syncthing;
  final Future<String>? appVersion;

  /// Shows the welcome screens again; hidden when null.
  final VoidCallback? onShowWelcome;

  /// Opens this app's page in Android Settings; false when it could not.
  final Future<bool> Function() openSettings;

  static const syncRowKey = Key('settings-sync-row');
  static const privacyRowKey = Key('settings-privacy-row');
  static const micRowKey = Key('settings-mic-row');
  static const aboutRowKey = Key('settings-about-row');

  /// Shown when Android Settings could not be opened.
  static const openSettingsFailedMessage =
      'Settings could not be opened. Open Settings › Apps › Echo Vault › '
      'Permissions.';

  Future<void> _openAndroidSettings(BuildContext context) async {
    final opened = await openSettings();
    if (opened || !context.mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        const SnackBar(content: Text(openSettingsFailedMessage)),
      );
  }

  void _push(BuildContext context, Widget screen) => Navigator.of(
    context,
  ).push(MaterialPageRoute<void>(builder: (_) => screen));

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    // The navigation bar floats over this screen; keep the list clear of it.
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    return EmberPage(
      child: Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.xs,
            EvSpace.md,
            EvSpace.xl + bottomInset,
          ),
          children: [
            const PageHeader(
              title: 'Settings',
              subtitle: 'Your PC, privacy and app information',
            ),
            if (syncthing case final client?) ...[
              const SectionLabel('Your PC'),
              GroupCard(
                children: [
                  InfoRow(
                    key: syncRowKey,
                    icon: Icons.computer_rounded,
                    title: 'Connect to your PC',
                    subtitle: 'Pair this phone and check the connection',
                    onTap: () => _push(
                      context,
                      SettingsScreen(syncthing: client, appVersion: appVersion),
                    ),
                  ),
                ],
              ),
            ],
            const SectionLabel('Privacy'),
            GroupCard(
              children: [
                InfoRow(
                  key: privacyRowKey,
                  icon: Icons.shield_outlined,
                  title: 'Processing & privacy',
                  subtitle: 'How your recordings are handled',
                  onTap: () => _push(context, const ProcessingPrivacyScreen()),
                ),
                InfoRow(
                  key: micRowKey,
                  icon: Icons.mic_none_rounded,
                  title: 'Microphone access',
                  subtitle:
                      'Used only while you record. Opens Android Settings to '
                      'allow or block it.',
                  onTap: () => unawaited(_openAndroidSettings(context)),
                ),
                const InfoRow(
                  icon: Icons.folder_outlined,
                  title: 'Recordings on this phone',
                  subtitle:
                      'Kept in Echo Vault’s private storage. To rename or '
                      'delete one, use its menu in Sessions.',
                ),
              ],
            ),
            const SectionLabel('App'),
            GroupCard(
              children: [
                if (onShowWelcome != null)
                  InfoRow(
                    icon: Icons.waving_hand_outlined,
                    iconColor: EvEmber.textSoft,
                    title: 'Show welcome screens',
                    subtitle: 'See the short introduction again',
                    onTap: onShowWelcome,
                  ),
                // Version and licences live in About.
                FutureBuilder<String>(
                  future: appVersion,
                  builder: (context, snapshot) => InfoRow(
                    key: aboutRowKey,
                    icon: Icons.info_outline_rounded,
                    iconColor: EvEmber.textSoft,
                    title: 'About Echo Vault',
                    subtitle: snapshot.data == null
                        ? 'Version and open-source licences'
                        : 'Version ${snapshot.data} · open-source licences',
                    onTap: () =>
                        _push(context, AboutScreen(appVersion: appVersion)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: EvSpace.xl),
            const Center(child: BrandSymbol(size: 28)),
            const SizedBox(height: EvSpace.xs),
            Text(
              EvBrand.tagline,
              textAlign: TextAlign.center,
              style: textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
            ),
          ],
        ),
      ),
      ),
    );
  }
}
