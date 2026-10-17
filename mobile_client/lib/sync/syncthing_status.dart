/// A snapshot of the embedded Syncthing, as reported by `syncthingStatus`
/// (see `SyncthingController.status()` in MainActivity's package). Pure Dart.
class SyncthingStatus {
  const SyncthingStatus({
    required this.running,
    this.error,
    this.exitCode,
    this.version,
    this.deviceId,
    this.lanOnlyVerified = false,
    this.lanOnly = const {},
    this.listeners = const [],
    this.discovery = const [],
    this.discoveryErrors = const [],
    this.folderId,
    this.folderPath,
    this.folderType,
    this.folderState,
    this.pcDeviceId,
    this.pcAddress,
    this.pcConnected = false,
    this.pcConnectionAddress,
    this.pcConnectionType,
    this.remoteState,
    this.pendingItems,
    this.pendingChunks,
    this.connections = const [],
  });

  factory SyncthingStatus.fromMap(Map<Object?, Object?> map) {
    List<String> strings(Object? value) => [
      for (final item in (value as List<Object?>?) ?? const []) '$item',
    ];
    return SyncthingStatus(
      running: map['running'] == true,
      error: map['error'] as String?,
      exitCode: map['exitCode'] as int?,
      version: map['version'] as String?,
      deviceId: map['deviceId'] as String?,
      lanOnlyVerified: map['lanOnlyVerified'] == true,
      lanOnly: {
        for (final MapEntry(:key, :value)
            in ((map['lanOnly'] as Map<Object?, Object?>?) ?? const {}).entries)
          '$key': value,
      },
      listeners: strings(map['listeners']),
      discovery: strings(map['discovery']),
      discoveryErrors: strings(map['discoveryErrors']),
      folderId: map['folderId'] as String?,
      folderPath: map['folderPath'] as String?,
      folderType: map['folderType'] as String?,
      folderState: map['folderState'] as String?,
      pcDeviceId: map['pcDeviceId'] as String?,
      pcAddress: map['pcAddress'] as String?,
      pcConnected: map['pcConnected'] == true,
      pcConnectionAddress: map['pcConnectionAddress'] as String?,
      pcConnectionType: map['pcConnectionType'] as String?,
      remoteState: map['remoteState'] as String?,
      pendingItems: map['pendingItems'] as int?,
      pendingChunks: map['pendingChunks'] as int?,
      connections: [
        for (final item in (map['connections'] as List<Object?>?) ?? const [])
          SyncConnection.fromMap(item! as Map<Object?, Object?>),
      ],
    );
  }

  final bool running;

  /// Why the last start failed, or why the status is incomplete.
  final String? error;

  /// Exit code of the last Syncthing process, once it has exited.
  final int? exitCode;
  final String? version;

  /// This phone's Syncthing device ID.
  final String? deviceId;

  /// The LAN-only options and the 127.0.0.1 GUI/REST address were read back
  /// from Syncthing and match what the app enforces.
  final bool lanOnlyVerified;

  /// The LAN-only option values as read back from Syncthing.
  final Map<String, Object?> lanOnly;

  /// Sync protocol listeners (e.g. `tcp://0.0.0.0:22000`).
  final List<String> listeners;

  /// Working discovery mechanisms (e.g. `IPv4 local`).
  final List<String> discovery;

  /// Discovery mechanisms that failed, as `name: error`.
  final List<String> discoveryErrors;

  final String? folderId;
  final String? folderPath;
  final String? folderType;

  /// Syncthing's folder state: `idle`, `scanning`, `sync-preparing`, …
  final String? folderState;

  final String? pcDeviceId;

  /// The PC's configured fixed address, `tcp://<ip>:<port>`.
  final String? pcAddress;
  final bool pcConnected;

  /// Remote end of the live connection to the PC, e.g. `192.168.1.20:22000`.
  final String? pcConnectionAddress;
  final String? pcConnectionType;

  /// Whether the PC shares the folder: `valid`, `notSharing`, `paused`,
  /// `unknown`.
  final String? remoteState;

  /// Files and directories the PC still needs.
  final int? pendingItems;

  /// Chunk audio files (`.opus`) the PC still needs.
  final int? pendingChunks;

  /// Live connections (any device).
  final List<SyncConnection> connections;

  bool get pcConfigured => pcDeviceId != null;

  /// One line for the connection: "PC connected", "PC not connected", …
  String get connectionLabel {
    if (!running) return 'Syncthing not running';
    if (!pcConfigured) return 'No PC set';
    if (!pcConnected) return 'PC not connected';
    if (remoteState == 'notSharing') {
      return 'PC connected · folder not accepted yet';
    }
    return 'PC connected';
  }

  /// "n chunks pending", or null before a PC is set.
  String? get pendingLabel => switch (pendingChunks) {
    null => null,
    1 => '1 chunk pending',
    final n => '$n chunks pending',
  };
}

/// One live Syncthing connection.
class SyncConnection {
  const SyncConnection({
    required this.deviceId,
    required this.address,
    required this.type,
  });

  factory SyncConnection.fromMap(Map<Object?, Object?> map) => SyncConnection(
    deviceId: '${map['deviceId']}',
    address: '${map['address']}',
    type: '${map['type']}',
  );

  final String deviceId;
  final String address;
  final String type;
}
