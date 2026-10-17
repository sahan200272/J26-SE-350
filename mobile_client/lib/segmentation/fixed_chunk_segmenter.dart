part of 'segmenter.dart';

/// Parameters of [FixedChunkSegmenter].
class FixedChunkConfig {
  const FixedChunkConfig({this.windowMs = 5000, this.minSpeechRatio = 0.1})
    : assert(windowMs >= 32 && windowMs <= 30000),
      assert(minSpeechRatio >= 0 && minSpeechRatio <= 1);

  /// Window length; rounded to whole 32 ms frames (5000 ms → 156 frames,
  /// 4.992 s).
  final int windowMs;

  /// A window is kept when at least this fraction of its frames is speech.
  final double minSpeechRatio;

  int get windowFrames =>
      math.max(1, (windowMs * kSampleRate / 1000 / kFrameSamples).round());

  Map<String, Object?> toJson() => {
    'window_ms': windowMs,
    'min_speech_ratio': minSpeechRatio,
  };

  factory FixedChunkConfig.fromJson(Map<String, Object?> json) =>
      FixedChunkConfig(
        windowMs: json['window_ms']! as int,
        minSpeechRatio: (json['min_speech_ratio']! as num).toDouble(),
      );

  @override
  bool operator ==(Object other) =>
      other is FixedChunkConfig &&
      other.windowMs == windowMs &&
      other.minSpeechRatio == minSpeechRatio;

  @override
  int get hashCode => Object.hash(windowMs, minSpeechRatio);

  @override
  String toString() => 'FixedChunkConfig(${toJson()})';
}

/// Baseline (proposal Table 5): fixed-length windows, kept only if the VAD
/// speech ratio reaches [FixedChunkConfig.minSpeechRatio]. The last window
/// of a run is shorter and judged the same way.
class FixedChunkSegmenter extends _SegmenterBase {
  FixedChunkSegmenter(super.vad, [this.settings = const FixedChunkConfig()])
    : super();

  FixedChunkSegmenter.forSession(
    super.vad,
    this.settings, {
    super.sessionId,
    super.sessionStartWallClock,
  });

  final FixedChunkConfig settings;
  final _window = <_Frame>[];

  @override
  String get type => 'fixed';

  @override
  Map<String, Object?> get config => settings.toJson();

  /// The latest frame was speech (this segmenter has no onset state).
  @override
  bool get inSpeech => lastDecision?.isSpeech ?? false;

  @override
  int get _framesPending => _window.length;

  @override
  List<Segment> _step(_Frame f) {
    _window.add(f);
    return _window.length >= settings.windowFrames ? _closeWindow() : const [];
  }

  @override
  List<Segment> _flush() => _window.isEmpty ? const [] : _closeWindow();

  List<Segment> _closeWindow() {
    final frames = List.of(_window);
    _window.clear();
    final speech = frames.where((f) => f.isSpeech).length;
    if (speech / frames.length >= settings.minSpeechRatio) {
      return [_emit(frames, forcedSplit: false)];
    }
    _exclude(frames);
    return const [];
  }
}
