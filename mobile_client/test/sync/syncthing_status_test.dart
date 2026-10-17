import 'package:echo_vault/sync/syncthing_status.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  // Shape of SyncthingController.status() over the channel.
  final full = <Object?, Object?>{
    'running': true,
    'error': null,
    'exitCode': null,
    'folderId': 'echo-vault-outbox',
    'folderPath': '/data/user/0/lk.sliit.j26se350.echo_vault/files/outbox',
    'version': 'v2.1.6',
    'deviceId': 'PHONE-ID',
    'guiAddress': '127.0.0.1:39525',
    'lanOnly': <Object?, Object?>{
      'globalAnnounceEnabled': false,
      'relaysEnabled': false,
      'listenAddresses': <Object?>['tcp://0.0.0.0:22000'],
    },
    'lanOnlyVerified': true,
    'listeners': <Object?>['tcp://0.0.0.0:22000'],
    'discovery': <Object?>['IPv4 local'],
    'discoveryErrors': <Object?>[
      'IPv6 local: route ip+net: netlinkrib: permission denied',
    ],
    'folderType': 'sendonly',
    'folderState': 'idle',
    'connections': <Object?>[
      <Object?, Object?>{
        'deviceId': 'PC-ID',
        'address': '192.168.1.20:22000',
        'type': 'tcp-client',
      },
    ],
    'pcDeviceId': 'PC-ID',
    'pcAddress': 'tcp://192.168.1.20:22000',
    'pcConnected': true,
    'pcConnectionAddress': '192.168.1.20:22000',
    'pcConnectionType': 'tcp-client',
    'remoteState': 'valid',
    'pendingItems': 4,
    'pendingChunks': 2,
  };

  test('parses every field of the status map', () {
    final s = SyncthingStatus.fromMap(full);
    expect(s.running, isTrue);
    expect(s.version, 'v2.1.6');
    expect(s.deviceId, 'PHONE-ID');
    expect(s.lanOnlyVerified, isTrue);
    expect(s.lanOnly['globalAnnounceEnabled'], isFalse);
    expect(s.lanOnly['listenAddresses'], ['tcp://0.0.0.0:22000']);
    expect(s.listeners, ['tcp://0.0.0.0:22000']);
    expect(s.discovery, ['IPv4 local']);
    expect(s.discoveryErrors.single, startsWith('IPv6 local:'));
    expect(s.folderType, 'sendonly');
    expect(s.folderState, 'idle');
    expect(s.pcDeviceId, 'PC-ID');
    expect(s.pcAddress, 'tcp://192.168.1.20:22000');
    expect(s.pcConnected, isTrue);
    expect(s.pcConnectionAddress, '192.168.1.20:22000');
    expect(s.pcConnectionType, 'tcp-client');
    expect(s.remoteState, 'valid');
    expect(s.pendingItems, 4);
    expect(s.pendingChunks, 2);
    expect(s.connections.single.address, '192.168.1.20:22000');
    expect(s.connections.single.type, 'tcp-client');
    expect(s.connectionLabel, 'PC connected');
    expect(s.pendingLabel, '2 chunks pending');
  });

  test('a stopped instance has only running, error and exit code', () {
    final s = SyncthingStatus.fromMap({
      'running': false,
      'error': 'REST API did not answer',
      'exitCode': 1,
      'folderId': 'echo-vault-outbox',
    });
    expect(s.running, isFalse);
    expect(s.error, 'REST API did not answer');
    expect(s.exitCode, 1);
    expect(s.lanOnlyVerified, isFalse);
    expect(s.listeners, isEmpty);
    expect(s.connections, isEmpty);
    expect(s.connectionLabel, 'Syncthing not running');
    expect(s.pendingLabel, isNull);
  });

  test('connection and pending labels', () {
    SyncthingStatus s({
      String? pc,
      bool connected = false,
      String? remote,
      int? pending,
    }) => SyncthingStatus(
      running: true,
      pcDeviceId: pc,
      pcConnected: connected,
      remoteState: remote,
      pendingChunks: pending,
    );
    expect(s().connectionLabel, 'No PC set');
    expect(s(pc: 'X').connectionLabel, 'PC not connected');
    expect(s(pc: 'X', connected: true).connectionLabel, 'PC connected');
    expect(
      s(pc: 'X', connected: true, remote: 'notSharing').connectionLabel,
      'PC connected · folder not accepted yet',
    );
    expect(s(pending: 0).pendingLabel, '0 chunks pending');
    expect(s(pending: 1).pendingLabel, '1 chunk pending');
    expect(s(pending: 7).pendingLabel, '7 chunks pending');
  });
}
