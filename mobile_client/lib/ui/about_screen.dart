import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'components.dart';
import 'theme/app_theme.dart';

/// The embedded Syncthing release; keep in step with `tool/fetch_syncthing.ps1`.
const kSyncthingVersion = 'v2.1.6';
const kSyncthingSourceUrl = 'https://github.com/syncthing/syncthing';
const kSyncthingReleaseUrl =
    'https://github.com/syncthing/syncthing/releases/tag/$kSyncthingVersion';

/// Syncthing's LICENSE.txt (MPL-2.0) from the pinned release, as shipped.
const kSyncthingLicenseAsset = 'assets/licenses/syncthing_LICENSE.txt';

Future<String> loadSyncthingLicense() =>
    rootBundle.loadString(kSyncthingLicenseAsset);

/// About: app version, the embedded Syncthing (version, MPL-2.0 licence text
/// and where to get its source, as MPL-2.0 §3.2 requires), and Flutter's
/// licence page for everything else.
class AboutScreen extends StatelessWidget {
  const AboutScreen({
    super.key,
    this.appVersion,
    this.syncthingVersion,
    this.licenseText = loadSyncthingLicense,
  });

  final Future<String>? appVersion;

  /// The running Syncthing's version, if known.
  final String? syncthingVersion;
  final Future<String> Function() licenseText;

  static const licenseKey = Key('syncthing-license');

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('About')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.md,
            EvSpace.md,
            EvSpace.xl,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
            EvCard(
              padding: const EdgeInsets.all(EvSpace.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const BrandLogo(height: 44),
                  const SizedBox(height: EvSpace.md),
                  Text(
                    EvBrand.tagline,
                    style: textTheme.titleSmall?.copyWith(
                      color: EvColors.teal,
                    ),
                  ),
                  const SizedBox(height: EvSpace.xs),
                  FutureBuilder<String>(
                    future: appVersion,
                    builder: (context, snapshot) => Text(
                      'Version ${snapshot.data ?? '…'}',
                      style: textTheme.bodySmall,
                    ),
                  ),
                  const SizedBox(height: EvSpace.sm),
                  Text(
                    'A privacy-preserving voice assistant. This app records '
                    'conversations when you choose and sends them to Echo '
                    'Vault on your own PC over your local network.',
                    style: textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
            const SizedBox(height: EvSpace.lg),
            Text('Syncthing', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'This app includes Syncthing $kSyncthingVersion'
              '${syncthingVersion != null && syncthingVersion != kSyncthingVersion ? ' (running: $syncthingVersion)' : ''}'
              ', the official, unmodified linux-arm64 executable from the '
              'Syncthing project, configured to work on the local network '
              'only. Syncthing is copyright The Syncthing Authors and is '
              'licensed under the Mozilla Public License 2.0, reproduced '
              'below. Its source code is available at:',
              style: textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            const _Link(label: 'Source code', url: kSyncthingSourceUrl),
            const _Link(
              label: 'This release ($kSyncthingVersion)',
              url: kSyncthingReleaseUrl,
            ),
            const SizedBox(height: 16),
            Text('Mozilla Public License 2.0', style: textTheme.titleSmall),
            const SizedBox(height: 8),
            FutureBuilder<String>(
              future: licenseText(),
              builder: (context, snapshot) {
                if (snapshot.hasError) {
                  return Text('Licence text unavailable: ${snapshot.error}');
                }
                final text = snapshot.data;
                if (text == null) return const LinearProgressIndicator();
                return Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: EvColors.surfaceLow,
                    border: Border.all(color: EvColors.border),
                    borderRadius: BorderRadius.circular(EvRadius.md),
                  ),
                  child: SelectableText(
                    key: licenseKey,
                    text,
                    style: const TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 11,
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: () => showLicensePage(
                context: context,
                applicationName: 'Echo Vault',
              ),
              child: const Text('Other open-source licences'),
            ),
          ],
          ),
        ),
      ),
    );
  }
}

/// A URL shown as selectable text with a copy button (the app opens no
/// browser itself).
class _Link extends StatelessWidget {
  const _Link({required this.label, required this.url});

  final String label;
  final String url;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelMedium),
              SelectableText(
                url,
                style: TextStyle(color: Theme.of(context).colorScheme.primary),
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'Copy link',
          icon: const Icon(Icons.copy),
          onPressed: () async {
            await Clipboard.setData(ClipboardData(text: url));
            if (context.mounted) {
              ScaffoldMessenger.of(context)
                  .showSnackBar(const SnackBar(content: Text('Link copied')));
            }
          },
        ),
      ],
    );
  }
}
