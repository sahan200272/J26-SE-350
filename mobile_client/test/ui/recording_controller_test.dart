import 'dart:async';
import 'dart:typed_data';

import 'package:echo_vault/capture/audio_capture.dart';
import 'package:echo_vault/capture/pcm_framer.dart';
import 'package:echo_vault/permissions/microphone_permission.dart';
import 'package:echo_vault/segmentation/segment.dart';
import 'package:echo_vault/session/recording_session.dart';
import 'package:echo_vault/ui/recording_controller.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_audio_capture.dart';
import '../helpers/fake_clock.dart';
import '../helpers/fake_lifecycle.dart';
import '../helpers/fake_microphone_permission.dart';
import '../helpers/fake_random.dart';
import '../helpers/fake_screen_awake.dart';
import '../helpers/pcm.dart';
import '../helpers/recording_frame_sink.dart';

const s1 = Duration(seconds: 1);

void main() {
  late FakeClock clock;
  late FakeAudioCapture capture;
  late FakeLifecycle lifecycle;
  late FakeScreenAwake screen;
  late FakeMicrophonePermission permission;
  late List<RecordingFrameSink> sinks;
  late List<String> logs;
  late RecordingController controller;
  late List<PcmFrame> frames;
  late List<Segment> segments;
  late List<(String, Segment)> sinkSegments;

  setUp(() {
    clock = FakeClock();
    capture = FakeAudioCapture();
    lifecycle = FakeLifecycle();
    screen = FakeScreenAwake();
    permission = FakeMicrophonePermission();
    sinks = [];
    logs = [];
    frames = [];
    segments = [];
    sinkSegments = [];
    controller = RecordingController(
      permission: permission,
      capture: capture,
      screenAwake: screen,
      lifecycle: lifecycle,
      clock: clock,
      wallClock: () => DateTime(2026, 10, 15, 14, 23, 0, 500),
      random: FakeRandom(0xa1b2),
      debugFrameSinkFactory: (id) {
        final sink = RecordingFrameSink(id);
        sinks.add(sink);
        return sink;
      },
      debugSegmentSinkFactory: (id) =>
          (segment) => sinkSegments.add((id, segment)),
      log: logs.add,
      // The ticker only refreshes the UI; keep it out of these tests.
      tickInterval: const Duration(hours: 1),
    );
    controller.frames.listen(frames.add);
    controller.segments.listen(segments.add);
  });

  tearDown(() => controller.dispose());

  /// Start, and let the capture start call complete.
  Future<void> startRecording() async {
    await controller.start();
    await pumpEventQueue();
  }

  test('Start: new session with ID and wall-clock start; capture started; '
      'screen kept on', () async {
    await startRecording();
    expect(controller.state, SessionState.recording);
    expect(controller.sessionId, '20261015T142300_a1b2');
    expect(controller.startWallClock, DateTime(2026, 10, 15, 14, 23, 0, 500));
    expect(capture.calls, ['start']);
    expect(screen.calls, [true]);
    expect(sinks.single.sessionId, '20261015T142300_a1b2');
    expect(controller.framer!.isOpen, isTrue);
  });

  test('denied permission: no session, no capture, screen untouched', () async {
    permission.status = MicPermissionStatus.denied;
    await startRecording();
    expect(controller.state, SessionState.idle);
    expect(capture.calls, isEmpty);
    expect(screen.calls, isEmpty);
    expect(sinks, isEmpty);
  });

  test('frames carry audio and session offsets', () async {
    await startRecording();
    capture.emitSamples(rampSamples(1000));
    expect(frames, hasLength(1));
    expect(frames.single.sessionOffset, Duration.zero);
    expect(sinks.single.frames, frames);
  });

  group('FR2: no frames while paused or stopped', () {
    test('zero frames while paused; capture paused; bytes dropped and '
        'counted', () async {
      await startRecording();
      capture.emitSamples(rampSamples(1024));
      expect(frames, hasLength(2));

      controller.pause();
      expect(controller.state, SessionState.paused);
      await pumpEventQueue();
      expect(capture.calls, ['start', 'pause']);
      expect(capture.running, isFalse);

      // The platform keeps delivering (late or misbehaving) while paused.
      final countBefore = frames.length;
      for (var i = 0; i < 10; i++) {
        capture.emitSamples(rampSamples(777));
      }
      capture.emit(constantPcm(3).sublist(0, 5)); // odd byte count

      expect(frames, hasLength(countBefore), reason: 'no frame while paused');
      expect(frames, hasLength(2));
      expect(controller.framer!.droppedBytes, 10 * 777 * 2 + 5);
      expect(controller.framer!.droppedChunks, 11);
      expect(logs.where((l) => l.contains('dropped')), hasLength(11));
      expect(sinks.single.frames, hasLength(2));
    });

    test('the partial frame at pause is flushed; resume continues the '
        'timelines', () async {
      await startRecording();
      capture.emitSamples(rampSamples(16000)); // 1 s of audio
      clock.advance(s1);
      controller.pause(); // paused at 1 s
      await pumpEventQueue();
      expect(frames, hasLength(32), reason: '31 full + 1 padded');
      expect(frames.last.validSamples, 16000 - 31 * 512);

      clock.advance(s1 * 4);
      capture.emitSamples(rampSamples(8000)); // dropped
      controller.resume(); // resumed at 5 s
      await pumpEventQueue();
      expect(capture.calls, ['start', 'pause', 'resume']);

      capture.emitSamples(rampSamples(1024, start: 16000));
      final afterResume = frames.skip(32).toList();
      expect(afterResume, hasLength(2));
      expect(afterResume.first.run, 1);
      expect(afterResume.first.sessionOffset, s1 * 5);
      expect(afterResume.first.audioOffsetSamples, 16000);
      expect(afterResume.first.audioOffset, s1);
      expect(
        afterResume.last.sessionOffset,
        const Duration(milliseconds: 5032),
      );
      expect(controller.framer!.droppedBytes, 16000);
    });

    test('Stop: capture stopped, screen released, late bytes dropped, '
        'debug sink closed after capture stop', () async {
      await startRecording();
      capture.emitSamples(rampSamples(600));
      final stopGate = Completer<void>();
      capture.gates['stop'] = stopGate;

      controller.stop();
      expect(controller.state, SessionState.stopped);
      expect(screen.calls, [true, false]);
      expect(frames, hasLength(2), reason: '512 + padded 88');

      // In flight while the platform is still stopping.
      capture.emitSamples(rampSamples(2048));
      expect(frames, hasLength(2));
      expect(sinks.single.closeCount, 0, reason: 'capture still stopping');

      stopGate.complete();
      await pumpEventQueue();
      expect(capture.calls, ['start', 'stop']);
      expect(sinks.single.closeCount, 1);
      expect(sinks.single.frames, hasLength(2));
      expect(controller.framer!.droppedBytes, 4096);
      expect(
        logs.where((l) => l.contains('finished')).single,
        allOf(contains('20261015T142300_a1b2'), contains('droppedBytes=4096')),
      );

      capture.emitSamples(rampSamples(100));
      expect(frames, hasLength(2));
    });

    test('pause and resume while capture.start is still pending', () async {
      final startGate = Completer<void>();
      capture.gates['start'] = startGate;
      await controller.start();
      await pumpEventQueue();
      expect(capture.calls, ['start']);

      clock.advance(s1);
      controller.pause();
      clock.advance(s1);
      controller.resume(); // second run begins at 2 s
      // Arrives before the capture has caught up: the framer is still
      // closed from the pause, so it is dropped.
      capture.emitSamples(rampSamples(512));
      expect(frames, isEmpty);
      expect(controller.framer!.droppedBytes, 1024);

      startGate.complete();
      await pumpEventQueue();
      // The capture missed a pause: it is paused, then resumed for run 2.
      expect(capture.calls, ['start', 'pause', 'resume']);
      capture.emitSamples(rampSamples(512));
      expect(frames.single.run, 1);
      expect(frames.single.sessionOffset, s1 * 2);
      expect(frames.single.audioOffsetSamples, 0);
    });
  });

  group('auto-pause on leaving the foreground', () {
    test('hidden while recording: paused with reason auto_background; '
        'capture paused; no frames', () async {
      await startRecording();
      capture.emitSamples(rampSamples(512));

      lifecycle
        ..emit(AppLifecycleState.inactive)
        ..emit(AppLifecycleState.hidden);
      expect(controller.state, SessionState.paused);
      expect(controller.pauseReason, PauseReason.autoBackground);
      expect(
        controller.pauseIntervals.single.reason,
        PauseReason.autoBackground,
      );
      await pumpEventQueue();
      expect(capture.calls, ['start', 'pause']);

      lifecycle.emit(AppLifecycleState.paused);
      capture.emitSamples(rampSamples(4096));
      expect(frames, hasLength(1));
      expect(screen.isOn, isTrue, reason: 'kept on while paused');
    });

    test('inactive alone (shade, dialog) does not pause', () async {
      await startRecording();
      lifecycle.emit(AppLifecycleState.inactive);
      expect(controller.state, SessionState.recording);
      lifecycle.emit(AppLifecycleState.resumed);
      expect(controller.state, SessionState.recording);
    });

    test('returning to the foreground does not resume', () async {
      await startRecording();
      lifecycle
        ..emit(AppLifecycleState.inactive)
        ..emit(AppLifecycleState.hidden)
        ..emit(AppLifecycleState.inactive)
        ..emit(AppLifecycleState.resumed);
      await pumpEventQueue();
      expect(controller.state, SessionState.paused);
      expect(controller.pauseReason, PauseReason.autoBackground);
      expect(capture.calls, ['start', 'pause']);

      controller.resume(); // user action
      await pumpEventQueue();
      expect(controller.state, SessionState.recording);
      expect(capture.calls, ['start', 'pause', 'resume']);
      expect(controller.pauseIntervals.single.isOpen, isFalse);
    });

    test('a user pause keeps its reason when the app is then hidden', () async {
      await startRecording();
      controller.pause();
      lifecycle.emit(AppLifecycleState.hidden);
      expect(controller.pauseReason, PauseReason.user);
      expect(controller.pauseIntervals, hasLength(1));
    });

    test('no effect when idle or stopped', () async {
      lifecycle.emit(AppLifecycleState.hidden);
      expect(controller.state, SessionState.idle);
      await startRecording();
      controller.stop();
      lifecycle.emit(AppLifecycleState.hidden);
      expect(controller.state, SessionState.stopped);
      expect(controller.pauseIntervals, isEmpty);
    });
  });

  test('screen kept on while recording or paused, released on stop', () async {
    await startRecording();
    controller.pause();
    controller.resume();
    expect(screen.calls, [true]);
    controller.stop();
    expect(screen.calls, [true, false]);
  });

  group('capture failures stop the session with a message', () {
    test('start throws', () async {
      capture.errors['start'] = const CaptureFailure('mic busy');
      await startRecording();
      expect(controller.state, SessionState.stopped);
      expect(controller.message, contains('mic busy'));
      expect(screen.calls, [true, false]);
      expect(capture.calls, ['start', 'stop']);
      expect(controller.framer!.isOpen, isFalse);
    });

    test('stream error while recording', () async {
      await startRecording();
      capture.emitSamples(rampSamples(700));
      capture.fail(const CaptureFailure('unsupported capture format'));
      expect(controller.state, SessionState.stopped);
      expect(
        controller.message,
        RecordingController.captureFailedMessage(
          const CaptureFailure('unsupported capture format'),
        ),
      );
      await pumpEventQueue();
      expect(capture.calls, ['start', 'stop']);
      expect(frames.map((f) => f.validSamples), [512, 188]);
    });

    test('the message clears on the next Start', () async {
      capture.errors['start'] = const CaptureFailure('mic busy');
      await startRecording();
      await startRecording();
      expect(controller.message, isNull);
      expect(controller.state, SessionState.recording);
    });
  });

  test(
    'Start after Stop: a new session; its framer starts from frame 0',
    () async {
      await startRecording();
      capture.emitSamples(rampSamples(1024));
      controller.stop();
      await pumpEventQueue();
      await startRecording();
      expect(capture.calls, ['start', 'stop', 'start']);
      capture.emitSamples(rampSamples(512));
      expect(frames.last.index, 0);
      expect(frames.last.audioOffsetSamples, 0);
      expect(sinks, hasLength(2));
      expect(sinks.first.closeCount, 1);
    },
  );

  test(
    'dispose stops capture, releases the screen and the lifecycle',
    () async {
      await startRecording();
      final c = controller;
      // Replace so tearDown does not dispose twice.
      controller = RecordingController(
        permission: permission,
        capture: FakeAudioCapture(),
        screenAwake: FakeScreenAwake(),
        lifecycle: FakeLifecycle(),
      );
      c.dispose();
      await pumpEventQueue();
      expect(capture.calls, ['start', 'stop']);
      expect(screen.calls, [true, false]);
      expect(lifecycle.isListening, isFalse);
      expect(sinks.single.closeCount, 1);
    },
  );

  test('input level is reported while recording only', () async {
    final ticking = RecordingController(
      permission: permission,
      capture: capture,
      screenAwake: screen,
      lifecycle: FakeLifecycle(),
      tickInterval: const Duration(milliseconds: 10),
    );
    addTearDown(ticking.dispose);
    await ticking.start();
    await pumpEventQueue();
    expect(ticking.inputLevelDbfs, isNull, reason: 'no frames yet');
    capture.emit(constantPcm(1600, 3277));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(ticking.inputLevelDbfs, closeTo(-20.0, 0.01));
    ticking.pause();
    expect(ticking.inputLevelDbfs, isNull);
  });

  group('capture startup delay (call → first PCM bytes), per run', () {
    test('measured for start and for each resume; kept on the session; '
        'logged', () async {
      clock.advance(s1 * 100); // non-zero clock origin
      await startRecording(); // capture.start called at t = 100 s
      clock.advance(const Duration(milliseconds: 140));
      capture.emitSamples(rampSamples(1280));
      clock.advance(const Duration(milliseconds: 80));
      capture.emitSamples(rampSamples(1280)); // later chunks don't count
      expect(controller.runs.single.captureStartDelay, ms(140));

      clock.advance(s1);
      controller.pause();
      clock.advance(s1 * 2);
      capture.emitSamples(rampSamples(1280)); // while paused: not a "first"
      controller.resume();
      await pumpEventQueue(); // capture.resume called now
      clock.advance(const Duration(microseconds: 95500));
      capture.emitSamples(rampSamples(1280));
      controller.stop();
      await pumpEventQueue();

      // Capture start = first-chunk arrival − 80 ms (1280 samples).
      expect(controller.runs, [
        RecordingRun(
          Duration.zero,
          captureStartDelay: ms(140),
          captureStartOffset: ms(60),
        ),
        RecordingRun(
          ms(3220),
          captureStartDelay: ms(95.5),
          captureStartOffset: ms(3235.5),
        ),
      ]);
      expect(logs.where((l) => l.contains('startup delay')), [
        '[capture] run 0 startup delay 140.0 ms '
            '(start/resume call → first 2560 B); capture start 60.0 ms '
            '(tap 0.0 ms)',
        '[capture] run 1 startup delay 95.5 ms '
            '(start/resume call → first 2560 B); capture start 3235.5 ms '
            '(tap 3220.0 ms)',
      ]);
      expect(
        logs.where((l) => l.contains('finished')).single,
        contains(
          'runs=[tap 0.0 ms / capture 60.0 ms (startup 140.0 ms), '
          'tap 3220.0 ms / capture 3235.5 ms (startup 95.5 ms)]',
        ),
      );
    });

    test('frames of each run count from the actual capture start', () async {
      await startRecording(); // tap and capture.start at 0
      clock.advance(const Duration(milliseconds: 700));
      capture.emitSamples(rampSamples(1280)); // arrives at 700 ms
      expect(frames.first.sessionOffset, ms(620)); // 700 − 80
      expect(frames[1].sessionOffset, ms(652));
      expect(frames.first.audioOffsetSamples, 0);

      clock.advance(s1);
      controller.pause(); // 1700 ms
      clock.advance(s1);
      controller.resume(); // tap at 2700 ms
      await pumpEventQueue();
      clock.advance(const Duration(milliseconds: 400));
      capture.emitSamples(rampSamples(1280, start: 1280)); // at 3100 ms
      final run1 = frames.where((f) => f.run == 1).toList();
      expect(run1.first.sessionOffset, ms(3020)); // 3100 − 80
      expect(run1.first.audioOffsetSamples, 1280);
    });

    test('a first chunk longer than its startup delay is clamped to the '
        'tap (never inside the pause)', () async {
      await startRecording();
      clock.advance(const Duration(milliseconds: 30));
      capture.emitSamples(rampSamples(1280)); // 80 ms of audio after 30 ms
      expect(controller.runs.single.captureStartOffset, Duration.zero);
      expect(frames.first.sessionOffset, Duration.zero);
      expect(controller.framer!.clampedAnchors, 1);
      expect(
        logs.where((l) => l.contains('startup delay')).single,
        endsWith(', raised to the tap'),
      );
    });

    test('"starting" until the first chunk of each run', () async {
      expect(controller.isStartingCapture, isFalse);
      await startRecording();
      expect(controller.isStartingCapture, isTrue);
      capture.emit(Uint8List(0)); // empty chunks do not count
      expect(controller.isStartingCapture, isTrue);
      capture.emitSamples(rampSamples(100));
      expect(controller.isStartingCapture, isFalse);
      controller.pause();
      expect(controller.isStartingCapture, isFalse, reason: 'paused');
      controller.resume();
      expect(controller.isStartingCapture, isTrue);
      await pumpEventQueue();
      capture.emitSamples(rampSamples(100));
      expect(controller.isStartingCapture, isFalse);
    });

    test('timed from the capture call, not from the Resume tap', () async {
      final pauseGate = Completer<void>();
      final resumeGate = Completer<void>();
      capture.gates['pause'] = pauseGate; // a slow native pause
      await startRecording();
      capture.emitSamples(rampSamples(512));
      controller.pause();
      clock.advance(s1);
      controller.resume(); // tapped while the pause call is still running
      clock.advance(const Duration(milliseconds: 300));
      capture.gates['resume'] = resumeGate;
      pauseGate.complete();
      await pumpEventQueue(); // resume called now (300 ms after the tap)
      clock.advance(const Duration(milliseconds: 50));
      capture.emitSamples(rampSamples(512));
      resumeGate.complete();
      await pumpEventQueue();
      expect(controller.runs.last.captureStartDelay, ms(50));
      // Tap at 1000 ms; first chunk (32 ms) arrived at 1350 ms.
      expect(controller.runs.last.startOffset, ms(1000));
      expect(controller.runs.last.captureStartOffset, ms(1318));
    });

    test('a run with no bytes before its pause keeps a null delay', () async {
      await startRecording();
      controller.pause();
      clock.advance(s1);
      capture.emitSamples(rampSamples(512)); // dropped: paused
      controller.resume();
      await pumpEventQueue();
      clock.advance(const Duration(milliseconds: 60));
      capture.emitSamples(rampSamples(512));
      expect(controller.runs.map((r) => r.captureStartDelay), [null, ms(60)]);
      expect(logs, contains('[capture] run 0: no PCM before pause'));
      expect(frames.single.run, 1, reason: 'frame.run = session run index');
    });

    test('runs skipped by the capture keep frame.run aligned with the '
        'session', () async {
      final startGate = Completer<void>();
      capture.gates['start'] = startGate;
      await controller.start();
      await pumpEventQueue();
      controller
        ..pause()
        ..resume() // run 1
        ..pause()
        ..resume(); // run 2
      startGate.complete();
      await pumpEventQueue();
      capture.emitSamples(rampSamples(512));
      expect(controller.runs, hasLength(3));
      expect(frames.single.run, 2);
      expect(controller.runs.map((r) => r.captureStartDelay != null), [
        false,
        false,
        true,
      ]);
    });
  });

  group('live segmentation (default VadSegmenter + EnergyVad)', () {
    // 32 ms frames: 512 samples. −20 dBFS tone vs digital silence.
    List<int> silence(int frames) => List.filled(frames * 512, 0);
    List<int> tone(int frames) => List.filled(frames * 512, 3277);

    test('one utterance → one segment with pre/post-roll; indicator and '
        'count follow; debug sink and log get it', () async {
      await startRecording();
      capture.emitSamples(silence(20));
      expect(controller.isSpeechDetected, isFalse);
      capture.emitSamples(tone(31));
      expect(controller.isSpeechDetected, isTrue);
      expect(controller.segmentCount, 0, reason: 'still open');
      capture.emitSamples(silence(25)); // hangover 19 frames ends it

      expect(controller.isSpeechDetected, isFalse);
      expect(controller.segmentCount, 1);
      final s = segments.single;
      // Pre-roll 10 frames before frame 20, post-roll 8 after frame 50.
      expect(s.audioStartSample, 10 * 512);
      expect(s.audioEndSample, (20 + 31 + 8) * 512);
      expect(s.sessionStart, ms(10 * 32));
      expect(s.sessionEnd, ms(59 * 32));
      expect(s.frameCount, 49);
      expect(s.speechFrameCount, 31);
      expect(s.run, 0);
      expect(s.seq, 0);
      expect(s.sessionId, '20261015T142300_a1b2');
      expect(
        s.startWallClock,
        DateTime(2026, 10, 15, 14, 23, 0, 500).add(ms(320)),
      );
      expect(s.samples.length, 49 * 512);
      expect(s.samples.sublist(10 * 512, 41 * 512), everyElement(3277));
      expect(sinkSegments.single, ('20261015T142300_a1b2', s));
      expect(
        logs.where((l) => l.startsWith('[segment] #0 run 0')),
        hasLength(1),
      );
    });

    test('Pause ends the open segment; nothing crosses the pause', () async {
      await startRecording();
      capture.emitSamples(silence(5) + tone(20));
      controller.pause(); // mid-speech
      expect(segments, hasLength(1), reason: 'closed at the pause');
      expect(segments.single.run, 0);
      expect(segments.single.audioEndSample, 25 * 512);

      clock.advance(s1 * 3);
      controller.resume();
      await pumpEventQueue();
      clock.advance(const Duration(milliseconds: 500));
      capture.emitSamples(tone(20) + silence(30));
      expect(segments, hasLength(2));
      final second = segments.last;
      expect(second.run, 1);
      expect(second.seq, 1);
      // Resumed at 3.0 s; first chunk (50 frames = 1.6 s) arrived at 3.5 s,
      // so capture started at max(3.5 − 1.6, 3.0) = 3.0 s (clamped).
      expect(second.sessionStart, s1 * 3);
      expect(second.audioStartSample, 25 * 512, reason: 'no pre-roll yet');
      for (final seg in segments) {
        final run = frames.where((f) => f.run == seg.run);
        expect(
          seg.audioStartSample,
          greaterThanOrEqualTo(run.first.audioOffsetSamples),
        );
        expect(
          seg.audioEndSample,
          lessThanOrEqualTo(
            run.last.audioOffsetSamples + run.last.validSamples,
          ),
        );
      }
    });

    test('NFR7 accounting balances at Stop and is logged', () async {
      await startRecording();
      capture.emitSamples(silence(7) + tone(2) + silence(9)); // too short
      capture.emitSamples(tone(40) + silence(3));
      controller.stop();
      await pumpEventQueue();
      final stats = controller.segmenter!.stats;
      expect(stats.framesSeen, frames.length);
      expect(stats.framesPending, 0);
      expect(stats.isBalanced, isTrue);
      expect(
        stats.framesInSegments +
            stats.framesInDiscardedSegments +
            stats.framesExcluded,
        frames.length,
      );
      expect(
        logs.where((l) => l.contains('finished')).single,
        contains('balanced: true'),
      );
    });

    test('a click shorter than the minimum is discarded and counted', () async {
      await startRecording();
      capture.emitSamples(silence(15) + tone(4) + silence(30));
      expect(segments, isEmpty);
      expect(controller.segmenter!.stats.segmentsDiscarded, 1);
      expect(controller.segmentCount, 0);
    });
  });
}

Duration ms(num milliseconds) =>
    Duration(microseconds: (milliseconds * 1000).round());
