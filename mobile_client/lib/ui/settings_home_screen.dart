import 'package:flutter/material.dart';

import '../sync/syncthing_client.dart';
import 'about_screen.dart';
import 'components.dart';
import 'processing_privacy_screen.dart';
import 'settings_screen.dart';
import 'theme/app_theme.dart';

/// Settings: the PC connection, privacy, and app information, in plain
/// language. Implementation details live in Processing & privacy.
class SettingsHomeScreen extends StatelessWidget {
  const SettingsHomeScreen({
    super.key,
    this.syncthing,
    this.appVersion,
    this.onShowWelcome,
  });

  final SyncthingClient? syncthing;
  final Future<String>? appVersion;

  /// Shows the welcome screens again; hidden when null.
  final VoidCallback? onShowWelcome;

  static const syncRowKey = Key('settings-sync-row');
  static const privacyRowKey = Key('settings-privacy-row');

  void _push(BuildContext context, Widget screen) => Navigator.of(
    context,
  ).push(MaterialPageRoute<void>(builder: (_) => screen));

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.xs,
            EvSpace.md,
            EvSpace.xl,
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
                const InfoRow(
                  icon: Icons.mic_none_rounded,
                  title: 'Microphone access',
                  subtitle:
                      'Asked the first time you record. Change it in Android '
                      'Settings › Apps › Echo Vault › Permissions.',
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
                    iconColor: EvColors.textMuted,
                    title: 'Show welcome screens',
                    onTap: onShowWelcome,
                  ),
                InfoRow(
                  icon: Icons.info_outline_rounded,
                  iconColor: EvColors.textMuted,
                  title: 'About Echo Vault',
                  subtitle: 'Version, licences and open source',
                  onTap: () =>
                      _push(context, AboutScreen(appVersion: appVersion)),
                ),
                InfoRow(
                  icon: Icons.tag_rounded,
                  iconColor: EvColors.textMuted,
                  title: 'Version',
                  trailing: FutureBuilder<String>(
                    future: appVersion,
                    builder: (context, snapshot) => Text(
                      snapshot.data ?? (appVersion == null ? '–' : '…'),
                      style: textTheme.bodyMedium?.copyWith(
                        color: EvColors.textMuted,
                      ),
                    ),
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
              style: textTheme.bodySmall?.copyWith(color: EvColors.textSubtle),
            ),
          ],
        ),
      ),
    );
  }
}
