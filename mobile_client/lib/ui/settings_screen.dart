import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../sync/peer_input.dart';
import '../sync/syncthing_client.dart';
import '../sync/syncthing_status.dart';
import 'about_screen.dart';
import 'components.dart';
import 'ember_components.dart';
import 'pc_link_card.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// "Connect to your PC" (A5) as a guided setup: the live connection status
/// at the top, then three numbered steps: (1) add this phone on the PC
/// (this phone's Syncthing device ID as text and QR), (2) enter the PC's
/// device ID and LAN address, (3) accept on the PC, with tips when it does
/// not connect. The status is refreshed every [pollInterval] while the
/// screen is open.
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

  /// After the first Save, the fields are checked while the user types.
  bool _checkLive = false;

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

  /// Checks both fields, shows what is wrong under each, and returns the
  /// canonical device ID and address when both are valid.
  (String, String)? _validate() {
    String? id;
    String? address;
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
    return id == null || address == null ? null : (id, address);
  }

  void _onFieldChanged() {
    setState(() {
      if (_checkLive) _validate();
    });
  }

  Future<void> _pasteId() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim();
    if (!mounted || text == null || text.isEmpty) return;
    _pcId.text = text;
    _onFieldChanged();
  }

  Future<void> _save() async {
    (String, String)? input;
    setState(() {
      _saveMessage = null;
      _checkLive = true;
      input = _validate();
    });
    final valid = input;
    if (valid == null) return;
    final (id, address) = valid;
    setState(() => _saving = true);
    try {
      final status = await widget.syncthing.setPeer(
        deviceId: id,
        address: address,
      );
      if (!mounted) return;
      setState(() {
        _status = status;
        _pcId.text = id;
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
    final status = _status;
    final configured = status?.pcConfigured ?? false;
    final linked =
        status != null &&
        status.running &&
        status.pcConnected &&
        status.remoteState != 'notSharing';
    return EmberPage(
      child: Scaffold(
        appBar: AppBar(
          // Opaque black: the top of the Ember background is black too.
          backgroundColor: EvEmber.black,
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
              _StatusCard(status: status, error: _statusError),
              const SizedBox(height: EvSpace.md),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: EvSpace.xxs),
                child: Text(
                  'Pair once. After that, recordings go from this phone to '
                  'your PC over your local network only. Your PC needs '
                  'Syncthing, which is part of the Echo Vault PC setup.',
                  style: Theme.of(
                    context,
                  ).textTheme.bodyMedium?.copyWith(color: EvEmber.textSoft),
                ),
              ),
              const SizedBox(height: EvSpace.md),
              StepCard(
                number: 1,
                title: 'Add this phone on your PC',
                subtitle:
                    'In Syncthing on the PC, choose Add Remote Device, then '
                    'scan this code or paste this phone’s ID.',
                done: linked,
                child: _ThisPhone(status: status, qr: _qr),
              ),
              const SizedBox(height: EvSpace.sm),
              StepCard(
                number: 2,
                title: 'Enter your PC’s details',
                subtitle:
                    'In Syncthing on the PC: Actions › Show ID. Find the '
                    'PC’s IP address with ipconfig. The PC must be on the '
                    'same Wi-Fi as this phone.',
                done: configured,
                child: _pcForm(context),
              ),
              const SizedBox(height: EvSpace.sm),
              StepCard(
                number: 3,
                title: 'Accept on your PC',
                done: linked,
                child: _AcceptStep(linked: linked, configured: configured),
              ),
              const SizedBox(height: EvSpace.md),
              GroupCard(
                children: [
                  InfoRow(
                    icon: Icons.description_outlined,
                    iconColor: EvEmber.textSoft,
                    title: 'About and licences',
                    subtitle: 'Version, open-source licences',
                    onTap: () => _openAbout(context),
                  ),
                ],
              ),
            ],
          ),
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

  Widget _pcForm(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    String? preview;
    try {
      preview = _pcIp.text.trim().isEmpty ? null : lanAddress(_pcIp.text);
    } on FormatException {
      preview = null;
    }
    final running = _status?.running == true;
    final String? disabledReason;
    if (_saving) {
      disabledReason = null;
    } else if (_status == null && _statusError == null) {
      disabledReason = 'Checking the PC link on this phone…';
    } else if (!running) {
      disabledReason =
          'Saving is possible once the PC link on this phone is running.';
    } else {
      disabledReason = null;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
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
            suffixIcon: IconButton(
              tooltip: 'Paste',
              icon: const Icon(Icons.content_paste_rounded),
              onPressed: () => unawaited(_pasteId()),
            ),
          ),
          style: const TextStyle(fontFamily: 'monospace'),
          textCapitalization: TextCapitalization.characters,
          autocorrect: false,
          enableSuggestions: false,
          maxLines: 2,
          minLines: 1,
          onChanged: (_) => _onFieldChanged(),
        ),
        const SizedBox(height: EvSpace.sm),
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
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          autocorrect: false,
          onChanged: (_) => _onFieldChanged(),
        ),
        const SizedBox(height: EvSpace.sm),
        FilledButton.icon(
          key: SettingsScreen.saveKey,
          onPressed: _saving || !running ? null : _save,
          icon: _saving
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.save_outlined),
          label: Text(_saving ? 'Saving…' : 'Save PC'),
        ),
        if (disabledReason != null) ...[
          const SizedBox(height: EvSpace.xs),
          Text(
            disabledReason,
            style: textTheme.bodySmall?.copyWith(color: EvEmber.textFaint),
          ),
        ],
        if (_saveMessage case final message?) ...[
          const SizedBox(height: EvSpace.xs),
          Text(
            key: SettingsScreen.saveMessageKey,
            message,
            style: textTheme.bodyMedium?.copyWith(color: Colors.white),
          ),
        ],
      ],
    );
  }
}

/// The live status at the top: a plain-language headline ([PcLinkInfo]),
/// then the details (connection, address, parts waiting, the LAN-only
/// check and a technical line).
class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.status, required this.error});

  final SyncthingStatus? status;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final s = status;
    final small = textTheme.bodySmall?.copyWith(color: EvEmber.textFaint);
    final info = PcLinkInfo.of(s);
    Widget detail(IconData icon, Widget text, {Color? color}) => Padding(
      padding: const EdgeInsets.only(top: EvSpace.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color ?? EvEmber.textSoft),
          const SizedBox(width: EvSpace.xs),
          Expanded(
            child: DefaultTextStyle.merge(
              style: textTheme.bodyMedium?.copyWith(color: Colors.white),
              child: text,
            ),
          ),
        ],
      ),
    );
    return Semantics(
      container: true,
      child: LiquidGlass(
        radius: 22,
        shadow: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (s == null && error == null) ...[
              Text(
                'Checking the connection…',
                style: textTheme.titleMedium?.copyWith(color: Colors.white),
              ),
              const SizedBox(height: EvSpace.sm),
              const LinearProgressIndicator(),
            ] else ...[
              Row(
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: info.color.withValues(alpha: 0.16),
                    ),
                    child: Icon(info.icon, size: 20, color: info.color),
                  ),
                  const SizedBox(width: EvSpace.sm),
                  Expanded(
                    // Announced when the connection changes; the details
                    // below (which refresh often) are not.
                    child: Semantics(
                      liveRegion: true,
                      label: '${info.title}. ${info.subtitle}',
                      excludeSemantics: true,
                      child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          info.title,
                          style: textTheme.titleMedium?.copyWith(
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          info.subtitle,
                          style: textTheme.bodySmall?.copyWith(
                            color: EvEmber.textSoft,
                          ),
                        ),
                      ],
                      ),
                    ),
                  ),
                ],
              ),
              if (s != null) ...[
                const SizedBox(height: EvSpace.sm),
                const Divider(color: EvEmber.hairline, height: 1),
                const SizedBox(height: EvSpace.xxs),
                detail(
                  s.running && s.pcConnected
                      ? Icons.link_rounded
                      : Icons.link_off_rounded,
                  Text(key: SettingsScreen.connectionKey, s.connectionLabel),
                ),
                if (s.pcConnected && s.pcConnectionAddress != null)
                  Padding(
                    padding: const EdgeInsets.only(left: 26, top: 2),
                    child: Text(
                      '${s.pcConnectionAddress} (${s.pcConnectionType})',
                      style: small,
                    ),
                  ),
                if (s.pendingLabel case final pending?)
                  detail(
                    s.pendingChunks == 0
                        ? Icons.cloud_done_outlined
                        : Icons.cloud_upload_outlined,
                    Text(key: SettingsScreen.pendingKey, pending),
                  ),
                if (s.running) ...[
                  detail(
                    s.lanOnlyVerified
                        ? Icons.lan_outlined
                        : Icons.warning_amber_rounded,
                    Text(
                      key: SettingsScreen.lanOnlyKey,
                      s.lanOnlyVerified
                          ? 'LAN-only settings verified'
                          : 'LAN-only settings NOT verified',
                    ),
                    color: s.lanOnlyVerified ? null : EvEmber.danger,
                  ),
                  Padding(
                    padding: const EdgeInsets.only(left: 26, top: 2),
                    child: Text(
                      'Syncthing ${s.version ?? ''} · folder ${s.folderState ?? '?'}'
                      ' · listening ${s.listeners.join(', ')}'
                      ' · discovery: ${s.discovery.join(', ')}'
                      '${s.discoveryErrors.isEmpty ? '' : ' (unavailable: ${s.discoveryErrors.map((e) => e.split(':').first).join(', ')})'}',
                      style: small,
                    ),
                  ),
                ],
              ],
            ],
            if (s?.error ?? error case final message?) ...[
              const SizedBox(height: EvSpace.xs),
              Text(
                message,
                style: textTheme.bodyMedium?.copyWith(
                  color: EvEmber.dangerText,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Step 1: this phone's device ID (text, Copy) and its QR code.
class _ThisPhone extends StatelessWidget {
  const _ThisPhone({required this.status, required this.qr});

  final SyncthingStatus? status;
  final Uint8List? qr;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final id = status?.deviceId;
    if (id == null) {
      return Text(
        'This phone’s ID appears once the PC link on this phone is running.',
        style: textTheme.bodyMedium?.copyWith(color: EvEmber.textSoft),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (qr case final png?)
          LayoutBuilder(
            builder: (context, box) {
              // As large as fits (easy to scan), up to 260 px.
              final size = math.min(260.0, box.maxWidth - 2 * EvSpace.sm);
              return Center(
                child: Container(
                  padding: const EdgeInsets.all(EvSpace.sm),
                  decoration: BoxDecoration(
                    color: EvColors.snow,
                    borderRadius: BorderRadius.circular(EvRadius.md),
                  ),
                  child: Image.memory(
                    key: SettingsScreen.qrKey,
                    png,
                    width: size,
                    height: size,
                    filterQuality: FilterQuality.none,
                    semanticLabel: 'QR code of this phone’s device ID',
                  ),
                ),
              );
            },
          ),
        const SizedBox(height: EvSpace.sm),
        SelectableText(
          key: SettingsScreen.deviceIdKey,
          id,
          style: const TextStyle(
            fontFamily: 'monospace',
            fontSize: 15,
            color: Colors.white,
          ),
        ),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: TextButton.icon(
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: id));
              if (context.mounted) {
                ScaffoldMessenger.of(context)
                  ..hideCurrentSnackBar()
                  ..showSnackBar(
                    const SnackBar(content: Text('Device ID copied')),
                  );
              }
            },
            style: TextButton.styleFrom(foregroundColor: Colors.white),
            icon: const Icon(Icons.copy_rounded, size: 18),
            label: const Text('Copy ID'),
          ),
        ),
      ],
    );
  }
}

/// Step 3: what to accept on the PC, a success state once connected, and
/// tips when it does not connect.
class _AcceptStep extends StatelessWidget {
  const _AcceptStep({required this.linked, required this.configured});

  final bool linked;
  final bool configured;

  static const tips = [
    'This phone and the PC are on the same Wi-Fi network.',
    'Syncthing is running on the PC.',
    'The PC’s IP address has not changed (check again with ipconfig).',
    'The PC’s firewall allows Syncthing.',
    'On the PC you accepted both the device and the folder.',
  ];

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    if (linked) {
      return Row(
        children: [
          const Icon(Icons.check_circle_rounded, color: EvEmber.success),
          const SizedBox(width: EvSpace.xs),
          Expanded(
            child: Text(
              'Connected. New recordings go to your PC by themselves.',
              style: textTheme.bodyMedium?.copyWith(color: Colors.white),
            ),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          configured
              ? 'Your PC now shows two requests. Accept the device “Echo '
                    'Vault”, then its folder “Echo Vault outbox”. This page '
                    'updates by itself.'
              : 'After step 2, your PC shows two requests: the device “Echo '
                    'Vault” and its folder “Echo Vault outbox”. Accept both.',
          style: textTheme.bodyMedium?.copyWith(color: EvEmber.textSoft),
        ),
        const SizedBox(height: EvSpace.xs),
        Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: const EdgeInsets.only(bottom: EvSpace.xs),
            iconColor: EvEmber.textSoft,
            collapsedIconColor: EvEmber.textSoft,
            title: Text(
              'Not connecting?',
              style: textTheme.titleSmall?.copyWith(color: Colors.white),
            ),
            children: [
              for (final tip in tips)
                Padding(
                  padding: const EdgeInsets.only(bottom: EvSpace.xs),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(top: 2),
                        child: Icon(
                          Icons.check_rounded,
                          size: 16,
                          color: EvEmber.textFaint,
                        ),
                      ),
                      const SizedBox(width: EvSpace.xs),
                      Expanded(
                        child: Text(
                          tip,
                          style: textTheme.bodyMedium?.copyWith(
                            color: EvEmber.textSoft,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
