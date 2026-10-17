import '../capture/pcm_framer.dart';

/// A VAD's verdict on one frame.
class VadDecision {
  const VadDecision({required this.isSpeech, required this.score});

  final bool isSpeech;

  /// Higher means more speech-like. The unit depends on the VAD; for
  /// [isSpeech] the VAD compares it against its own threshold.
  final double score;

  @override
  String toString() =>
      'VadDecision(${isSpeech ? 'speech' : 'non-speech'}, '
      '${score.toStringAsFixed(2)})';
}

/// Voice activity detector: classifies 32 ms frames in order (FR3).
///
/// Implementations are interchangeable behind this interface (CLAUDE.md):
/// the energy baseline now, a neural VAD later. Pure Dart.
abstract interface class Vad {
  /// Short identifier for segment metadata, e.g. `energy`.
  String get type;

  /// Parameters as JSON-encodable values, for segment metadata.
  Map<String, Object?> get config;

  /// Classifies [frame] using only its first [PcmFrame.validSamples]
  /// samples (the rest of a padded frame is zeros). Frames must be passed in
  /// order; a VAD may adapt to what it has seen.
  VadDecision classify(PcmFrame frame);

  /// Forgets everything learned (for a new session).
  void reset();
}
