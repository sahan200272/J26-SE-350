import 'package:flutter/material.dart';

import '../sync/syncthing_status.dart';
import 'components.dart';
import 'theme/app_theme.dart';

/// Plain-language description of the link to the user's PC, derived from
/// the embedded Syncthing status (no technical terms).
class PcLinkInfo {
  const PcLinkInfo(this.icon, this.title, this.subtitle, this.color);

  final IconData icon;
  final String title;
  final String subtitle;
  final Color color;

  factory PcLinkInfo.of(SyncthingStatus? s) {
    if (s == null) {
      return const PcLinkInfo(
        Icons.help_outline_rounded,
        'PC connection status unavailable',
        'Recordings stay safely on this phone.',
        EvColors.textMuted,
      );
    }
    if (!s.running) {
      return const PcLinkInfo(
        Icons.link_off_rounded,
        'PC link is not running',
        'Recordings stay on this phone until it restarts.',
        EvColors.warning,
      );
    }
    if (!s.pcConfigured) {
      return const PcLinkInfo(
        Icons.add_link_rounded,
        'Not connected to a PC yet',
        'Pair once to send recordings to your PC.',
        EvColors.warning,
      );
    }
    if (!s.pcConnected) {
      return const PcLinkInfo(
        Icons.wifi_off_rounded,
        'Your PC is not reachable',
        'Recordings wait on this phone until your PC is on the same network.',
        EvColors.textMuted,
      );
    }
    if (s.remoteState == 'notSharing') {
      return const PcLinkInfo(
        Icons.hourglass_top_rounded,
        'Waiting for your PC to accept',
        'Accept Echo Vault on your PC to start sending.',
        EvColors.warning,
      );
    }
    final pending = s.pendingChunks ?? 0;
    if (pending > 0) {
      return PcLinkInfo(
        Icons.upload_rounded,
        'Sending to your PC',
        '$pending ${pending == 1 ? 'part' : 'parts'} left to send',
        EvColors.teal,
      );
    }
    return const PcLinkInfo(
      Icons.check_circle_outline_rounded,
      'Up to date with your PC',
      'Every recording has been sent.',
      EvColors.success,
    );
  }
}

/// Compact card showing [PcLinkInfo]; opens the pairing screen on tap.
class PcLinkCard extends StatelessWidget {
  const PcLinkCard({super.key, required this.status, this.onTap});

  final SyncthingStatus? status;
  final VoidCallback? onTap;

  static const cardKey = Key('pc-link-card');

  @override
  Widget build(BuildContext context) {
    final info = PcLinkInfo.of(status);
    return EvCard(
      key: cardKey,
      padding: EdgeInsets.zero,
      child: InfoRow(
        icon: info.icon,
        iconColor: info.color,
        title: info.title,
        subtitle: info.subtitle,
        onTap: onTap,
      ),
    );
  }
}
