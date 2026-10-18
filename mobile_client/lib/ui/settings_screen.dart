import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../sync/peer_input.dart';
import '../sync/syncthing_client.dart';
import '../sync/syncthing_status.dart';
import 'about_screen.dart';
import 'components.dart';
import 'theme/app_theme.dart';

/// Sync settings (A5): this phone's Syncthing device ID (text and QR), the
/// PC's device ID and fixed LAN address, and the live connection and sync
/// status, refreshed every [pollInterval] while the screen is open.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({
    super.key,
    required this.syncthing,
    this.appVersion,
    this.pollInterval = const Duration(seconds: 2),
  });

  final SyncthingClient syncthing;
  final Future<String>? appVersion;
  final Duration pollInterval;

  static const connectionKey = Key('sync-connection');
  static const pendingKey = Key('sync-pending');
  static const lanOnlyKey = Key('sync-lan-only');
  static const deviceIdKey = Key('sync-device-id');
  static const qrKey = Key('sync-qr');
  static const pcIdFieldKey = Key('pc-device-id-field');
  static const pcIpFieldKey = Key('pc-ip-field');
  static const saveKey = Key('save-pc');
  static const saveMessageKey = Key('save-message');

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _pcId = TextEditingController();
  final _pcIp = TextEditingController();
  Timer? _timer;
  bool _refreshing = false;
  SyncthingStatus? _status;
  String? _statusError;
  Uint8List? _qr;
  String? _qrFor;
  bool _fieldsFilled = false;
  String? _pcIdError;
  String? _pcIpError;
  bool _saving = false;
  String? _saveMessage;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
    _timer = Timer.periodic(widget.pollInterval, (_) => unawaited(_refresh()));
  }

  @override
  void dispose() {
    _timer?.cancel();
    _pcId.dispose();
    _pcIp.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    if (_refreshing) return;
    _refreshing = true;
    try {
      final status = await widget.syncthing.status();
      if (!mounted) return;
      setState(() {
        _status = status;
        _statusError = null;
        _fillFieldsOnce(status);
      });
      final id = status.deviceId;
      if (id != null && id != _qrFor) {
        _qrFor = id;
        final png = await widget.syncthing.qrPng();
        if (mounted) setState(() => _qr = png);
      }
    } catch (e) {
      if (mounted) setState(() => _statusError = '$e');
    } finally {
      _refreshing = false;
    }
  }

  /// Shows the saved PC (from Syncthing's config) in the fields, once.
  void _fillFieldsOnce(SyncthingStatus status) {
    if (_fieldsFilled || !status.running) return;
    _fieldsFilled = true;
    if (status.pcDeviceId case final id?) _pcId.text = id;
    if (status.pcAddress case final address?) {
      _pcIp.text = address.replaceFirst('tcp://', '');
    }
  }

  Future<void> _save() async {
    String? id;
    String? address;
    setState(() {
      _saveMessage = null;
      try {
        id = normalizeDeviceId(_pcId.text);
        _pcIdError = null;
      } on FormatException catch (e) {
        _pcIdError = e.message;
      }
      try {
        address = lanAddress(_pcIp.text);
        _pcIpError = null;
      } on FormatException catch (e) {
        _pcIpError = e.message;
      }
    });
    if (id == null || address == null) return;
    setState(() => _saving = true);
    try {
      final status = await widget.syncthing.setPeer(
        deviceId: id!,
        address: address!,
      );
      if (!mounted) return;
      setState(() {
        _status = status;
        _pcId.text = id!;
        _saveMessage =
            'Saved. On the PC, accept the device “Echo Vault” and its '
            'folder “Echo Vault outbox”.';
      });
    } on PlatformException catch (e) {
      if (mounted) setState(() => _saveMessage = e.message ?? e.code);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Connect to your PC'),
        actions: [
          IconButton(
            tooltip: 'About',
            icon: const Icon(Icons.info_outline),
            onPressed: () => _openAbout(context),
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.xs,
            EvSpace.md,
            EvSpace.xl,
          ),
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: EvSpace.xxs),
              child: Text(
                'Pair once with your PC. After that, recordings move from '
                'this phone to your PC over your local network only. Your PC '
                'needs Syncthing installed (part of the Echo Vault PC '
                'setup).',
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
              ),
            ),
            const SizedBox(height: EvSpace.md),
            _StatusCard(status: _status, error: _statusError),
            const SizedBox(height: EvSpace.md),
            _ThisPhoneCard(status: _status, qr: _qr),
            const SizedBox(height: EvSpace.md),
            _pcCard(context),
            const SizedBox(height: EvSpace.md),
            GroupCard(
              children: [
                InfoRow(
                  icon: Icons.description_outlined,
                  iconColor: EvColors.textMuted,
                  title: 'About and licences',
                  onTap: () => _openAbout(context),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _openAbout(BuildContext context) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => AboutScreen(
        appVersion: widget.appVersion,
        syncthingVersion: _status?.version,
      ),
    ),
  );

  Widget _pcCard(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    String? preview;
    try {
      preview = _pcIp.text.trim().isEmpty ? null : lanAddress(_pcIp.text);
    } on FormatException {
      preview = null;
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Your PC', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'In Syncthing on the PC: Actions → Show ID. Find the PC’s IP '
              'with ipconfig (same Wi-Fi network as this phone).',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            TextField(
              key: SettingsScreen.pcIdFieldKey,
              controller: _pcId,
              decoration: InputDecoration(
                labelText: 'PC device ID',
                hintText: 'XXXXXXX-XXXXXXX-…',
                errorText: _pcIdError,
                errorMaxLines: 3,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(EvRadius.md),
                ),
              ),
              style: const TextStyle(fontFamily: 'monospace'),
              textCapitalization: TextCapitalization.characters,
              autocorrect: false,
              enableSuggestions: false,
              maxLines: 2,
              minLines: 1,
            ),
            const SizedBox(height: 12),
            TextField(
              key: SettingsScreen.pcIpFieldKey,
              controller: _pcIp,
              decoration: InputDecoration(
                labelText: 'PC IP address',
                hintText: '192.168.1.20',
                helperText: preview == null ? null : 'Address: $preview',
                errorText: _pcIpError,
                errorMaxLines: 3,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(EvRadius.md),
                ),
              ),
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              autocorrect: false,
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: SettingsScreen.saveKey,
              onPressed: _saving || _status?.running != true ? null : _save,
              icon: _saving
                  ? const SizedBox.square(
                      dimension: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: const Text('Save PC'),
            ),
            if (_saveMessage case final message?) ...[
              const SizedBox(height: 8),
              Text(key: SettingsScreen.saveMessageKey, message),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.status, required this.error});

  final SyncthingStatus? status;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final s = status;
    final connected = s != null && s.running && s.pcConnected;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Connection', style: textTheme.titleMedium),
            const SizedBox(height: 8),
            if (s == null && error == null)
              const LinearProgressIndicator()
            else if (s != null) ...[
              Row(
                children: [
                  Icon(
                    connected ? Icons.link : Icons.link_off,
                    color: connected ? scheme.primary : scheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      key: SettingsScreen.connectionKey,
                      s.connectionLabel,
                      style: textTheme.titleMedium,
                    ),
                  ),
                ],
              ),
              if (s.pcConnected && s.pcConnectionAddress != null)
                Padding(
                  padding: const EdgeInsets.only(left: 32, top: 2),
                  child: Text(
                    '${s.pcConnectionAddress} (${s.pcConnectionType})',
                    style: textTheme.bodySmall,
                  ),
                ),
              if (s.pendingLabel case final pending?) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(
                      s.pendingChunks == 0
                          ? Icons.cloud_done_outlined
                          : Icons.cloud_upload_outlined,
                      color: scheme.onSurfaceVariant,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      key: SettingsScreen.pendingKey,
                      pending,
                      style: textTheme.bodyLarge,
                    ),
                  ],
                ),
              ],
              if (s.running) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(
                      s.lanOnlyVerified ? Icons.lan_outlined : Icons.warning,
                      color: s.lanOnlyVerified
                          ? scheme.onSurfaceVariant
                          : scheme.error,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        key: SettingsScreen.lanOnlyKey,
                        s.lanOnlyVerified
                            ? 'LAN-only settings verified'
                            : 'LAN-only settings NOT verified',
                      ),
                    ),
                  ],
                ),
                Padding(
                  padding: const EdgeInsets.only(left: 32, top: 2),
                  child: Text(
                    'Syncthing ${s.version ?? ''} · folder ${s.folderState ?? '?'}'
                    ' · listening ${s.listeners.join(', ')}'
                    ' · discovery: ${s.discovery.join(', ')}'
                    '${s.discoveryErrors.isEmpty ? '' : ' (unavailable: ${s.discoveryErrors.map((e) => e.split(':').first).join(', ')})'}',
                    style: textTheme.bodySmall,
                  ),
                ),
              ],
            ],
            if (s?.error ?? error case final message?) ...[
              const SizedBox(height: 8),
              Text(message, style: TextStyle(color: scheme.error)),
            ],
          ],
        ),
      ),
    );
  }
}

class _ThisPhoneCard extends StatelessWidget {
  const _ThisPhoneCard({required this.status, required this.qr});

  final SyncthingStatus? status;
  final Uint8List? qr;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final id = status?.deviceId;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('This phone', style: textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'On the PC: Add Remote Device, then paste or scan this ID.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            if (id == null)
              const Text('Device ID appears once Syncthing is running.')
            else ...[
              SelectableText(
                key: SettingsScreen.deviceIdKey,
                id,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 15),
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: id));
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Device ID copied')),
                      );
                    }
                  },
                  icon: const Icon(Icons.copy),
                  label: const Text('Copy'),
                ),
              ),
              if (qr case final png?)
                Center(
                  child: Container(
                    padding: const EdgeInsets.all(EvSpace.sm),
                    decoration: BoxDecoration(
                      color: EvColors.snow,
                      borderRadius: BorderRadius.circular(EvRadius.md),
                    ),
                    child: Image.memory(
                      key: SettingsScreen.qrKey,
                      png,
                      width: 220,
                      height: 220,
                      filterQuality: FilterQuality.none,
                      semanticLabel: 'QR code of this phone’s device ID',
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
