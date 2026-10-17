import 'dart:collection';
import 'dart:math' as math;

import '../capture/audio_capture.dart';
import '../capture/level_meter.dart';
import '../capture/pcm_framer.dart';
import 'vad.dart';

/// Parameters of [EnergyVad]. All levels are RMS in dBFS (see `rmsDbfs`).
class EnergyVadConfig {
  const EnergyVadConfig({
    this.marginDb = 12,
    this.absoluteMinDbfs = -50,
    this.noiseWindowMs = 3000,
    this.initialNoiseFloorDbfs = -60,
  }) : assert(marginDb >= 0),
       assert(noiseWindowMs >= 32);

  /// A frame is speech when its level is at least this far above the noise
  /// floor...
  final double marginDb;

  /// ...and at least this loud, whatever the floor (e.g. after digital
  /// silence, where the floor would otherwise be −96 dBFS).
  final double absoluteMinDbfs;

  /// The noise floor is the quietest frame level within this trailing
  /// window (minimum tracking), so it follows a changing background within
  /// about this time, while short pauses between words keep it low during
  /// speech.
  final int noiseWindowMs;

  /// Floor assumed before a full window has been seen, so that speech in
  /// the very first frames is still detected. Null: start from the first
  /// frame's level.
  final double? initialNoiseFloorDbfs;

  /// Trailing window length in frames.
  int get noiseWindowFrames =>
      math.max(1, (noiseWindowMs * kSampleRate / 1000 / kFrameSamples).round());

  Map<String, Object?> toJson() => {
    'margin_db': marginDb,
    'absolute_min_dbfs': absoluteMinDbfs,
    'noise_window_ms': noiseWindowMs,
    'initial_noise_floor_dbfs': initialNoiseFloorDbfs,
  };

  factory EnergyVadConfig.fromJson(Map<String, Object?> json) =>
      EnergyVadConfig(
        marginDb: (json['margin_db']! as num).toDouble(),
        absoluteMinDbfs: (json['absolute_min_dbfs']! as num).toDouble(),
        noiseWindowMs: json['noise_window_ms']! as int,
        initialNoiseFloorDbfs: (json['initial_noise_floor_dbfs'] as num?)
            ?.toDouble(),
      );

  EnergyVadConfig copyWith({
    double? marginDb,
    double? absoluteMinDbfs,
    int? noiseWindowMs,
    ({double? value})? initialNoiseFloorDbfs,
  }) => EnergyVadConfig(
    marginDb: marginDb ?? this.marginDb,
    absoluteMinDbfs: absoluteMinDbfs ?? this.absoluteMinDbfs,
    noiseWindowMs: noiseWindowMs ?? this.noiseWindowMs,
    initialNoiseFloorDbfs: initialNoiseFloorDbfs != null
        ? initialNoiseFloorDbfs.value
        : this.initialNoiseFloorDbfs,
  );

  @override
  bool operator ==(Object other) =>
      other is EnergyVadConfig &&
      other.marginDb == marginDb &&
      other.absoluteMinDbfs == absoluteMinDbfs &&
      other.noiseWindowMs == noiseWindowMs &&
      other.initialNoiseFloorDbfs == initialNoiseFloorDbfs;

  @override
  int get hashCode => Object.hash(
    marginDb,
    absoluteMinDbfs,
    noiseWindowMs,
    initialNoiseFloorDbfs,
  );

  @override
  String toString() => 'EnergyVadConfig(${toJson()})';
}

/// Energy VAD (baseline): frame RMS in dBFS against an adaptive noise floor
/// plus a margin, never below an absolute minimum.
///
/// `threshold = max(floor + marginDb, absoluteMinDbfs)`; speech when
/// `level ≥ threshold`. [VadDecision.score] is `level − threshold` in dB.
class EnergyVad implements Vad {
  EnergyVad([this.settings = const EnergyVadConfig()]);

  final EnergyVadConfig settings;

  // Sliding-window minimum: (frame number, level), levels increasing.
  final _window = ListQueue<(int, double)>();
  int _frames = 0;

  double? _lastLevel;
  double? _lastFloor;
  double? _lastThreshold;

  /// Level, noise floor and threshold of the last classified frame (dBFS).
  double? get lastLevelDbfs => _lastLevel;
  double? get lastNoiseFloorDbfs => _lastFloor;
  double? get lastThresholdDbfs => _lastThreshold;

  @override
  String get type => 'energy';

  @override
  Map<String, Object?> get config => settings.toJson();

  @override
  VadDecision classify(PcmFrame frame) {
    final level = rmsDbfs(frame.samples, frame.validSamples);
    final n = _frames++;
    while (_window.isNotEmpty && _window.last.$2 >= level) {
      _window.removeLast();
    }
    _window.addLast((n, level));
    final windowFrames = settings.noiseWindowFrames;
    while (_window.first.$1 <= n - windowFrames) {
      _window.removeFirst();
    }

    var floor = _window.first.$2;
    final seed = settings.initialNoiseFloorDbfs;
    if (seed != null && n < windowFrames) floor = math.min(floor, seed);

    final threshold = math.max(
      floor + settings.marginDb,
      settings.absoluteMinDbfs,
    );
    _lastLevel = level;
    _lastFloor = floor;
    _lastThreshold = threshold;
    return VadDecision(isSpeech: level >= threshold, score: level - threshold);
  }

  @override
  void reset() {
    _window.clear();
    _frames = 0;
    _lastLevel = _lastFloor = _lastThreshold = null;
  }
}
