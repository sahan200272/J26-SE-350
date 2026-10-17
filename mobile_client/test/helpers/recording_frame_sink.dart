import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/capture/wav_writer.dart';

/// [FrameSink] that keeps every frame in memory.
class RecordingFrameSink implements FrameSink {
  RecordingFrameSink(this.sessionId);

  final String sessionId;
  final List<PcmFrame> frames = [];
  int closeCount = 0;

  @override
  void add(PcmFrame frame) {
    if (closeCount > 0) throw StateError('add after close');
    frames.add(frame);
  }

  @override
  Future<void> close() async => closeCount++;
}
