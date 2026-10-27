import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/segmentation/segment.dart';
import 'package:echo_vault/segmentation/segmenter.dart';
import 'package:echo_vault/session/recording_session.dart';
import 'package:echo_vault/vad/energy_vad.dart';

import 'fake_clock.dart';
import 'fake_random.dart';
import 'pcm.dart';

/// A recorded session built the way the app builds it: runs anchored at the
/// first chunk, frames through a real framer and the default segmenter,
/// pauses and stop on a fake clock. Session ID `20261018T100000_a1b2`.
class SessionFixture {
  SessionFixture() {
    session = RecordingSession(
      clock: clock,
      wallClock: () => DateTime(2026, 10, 18, 10, 0, 0),
      random: FakeRandom(0xa1b2),
    )..start();
    segmenter = VadSegmenter.forSession(
      EnergyVad(),
      const VadSegmenterConfig(),
      sessionId: session.id,
      sessionStartWallClock: session.startWallClock,
    );
  }

  final clock = FakeClock();
  late final RecordingSession session;
  final framer = PcmFramer();
  late final Segmenter segmenter;
  final segments = <Segment>[];

  /// Captures [samples] as the current run: the first 2560 B chunk arrives
  /// [startup] after the tap, the rest follows in real time.
  void capture(
    List<int> samples, {
    Duration startup = const Duration(milliseconds: 400),
  }) {
    final run = session.runCount - 1;
    framer.openAtFirstChunk(run: run, notBefore: session.runStartOffset!);
    final bytes = pcmBytes(samples);
    final callAt = clock.now();
    clock.advance(startup);
    final first = bytes.sublist(0, 2560);
    _take(framer.add(first, arrivedAt: session.offsetAt(clock.now())));
    session.setCaptureStart(
      run,
      delay: clock.now() - callAt,
      captureStartOffset: framer.runStartOffset!,
    );
    _take(framer.add(bytes.sublist(2560)));
    clock.advance(samplesToDuration((bytes.length - 2560) ~/ 2));
  }

  void pause([PauseReason reason = PauseReason.user]) {
    _endRun();
    session.pause(reason);
  }

  void resume({Duration after = const Duration(seconds: 3)}) {
    clock.advance(after);
    session.resume();
  }

  void stop() {
    _endRun();
    session.stop();
  }

  RecordingRun runOf(Segment s) => session.runs[s.run];

  void _endRun() {
    _take(framer.close());
    segments.addAll(segmenter.endRun());
  }

  void _take(List<PcmFrame> frames) {
    for (final f in frames) {
      segments.addAll(segmenter.add(f));
    }
  }
}
