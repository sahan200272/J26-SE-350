import 'package:echo_vault/session/recording_session.dart';
import 'package:echo_vault/session/session_id.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_clock.dart';
import '../helpers/fake_random.dart';

/// Drives a fresh session into [state] using only valid events.
RecordingSession sessionIn(SessionState state, {FakeClock? clock}) {
  final s = RecordingSession(clock: clock ?? FakeClock());
  switch (state) {
    case SessionState.idle:
      break;
    case SessionState.recording:
      s.start();
    case SessionState.paused:
      s
        ..start()
        ..pause();
    case SessionState.stopped:
      s
        ..start()
        ..stop();
  }
  return s;
}

const validTransitions = {
  (SessionState.idle, SessionEvent.start): SessionState.recording,
  (SessionState.recording, SessionEvent.pause): SessionState.paused,
  (SessionState.recording, SessionEvent.stop): SessionState.stopped,
  (SessionState.paused, SessionEvent.resume): SessionState.recording,
  (SessionState.paused, SessionEvent.stop): SessionState.stopped,
};

const s1 = Duration(seconds: 1);

void main() {
  test('new session is idle with zero time and no pauses', () {
    final s = RecordingSession(clock: FakeClock());
    expect(s.state, SessionState.idle);
    expect(s.recordedDuration, Duration.zero);
    expect(s.totalDuration, Duration.zero);
    expect(s.pauseIntervals, isEmpty);
    expect(s.allowedEvents, [SessionEvent.start]);
  });

  group('transition table: every (state, event) pair', () {
    for (final from in SessionState.values) {
      for (final event in SessionEvent.values) {
        final expected = validTransitions[(from, event)];
        if (expected != null) {
          test('VALID   ${from.name} --${event.name}--> ${expected.name}', () {
            final s = sessionIn(from);
            expect(s.canHandle(event), isTrue);
            s.handle(event);
            expect(s.state, expected);
          });
        } else {
          test('INVALID ${from.name} --${event.name}--> rejected', () {
            final s = sessionIn(from);
            final pausesBefore = s.pauseIntervals;
            expect(s.canHandle(event), isFalse);
            expect(
              () => s.handle(event),
              throwsA(
                isA<InvalidTransitionError>()
                    .having((e) => e.from, 'from', from)
                    .having((e) => e.event, 'event', event)
                    .having(
                      (e) => e.message,
                      'message',
                      startsWith(
                        'Cannot ${event.name} a session that is ${from.name}.',
                      ),
                    ),
              ),
            );
            expect(s.state, from, reason: 'state must not change');
            expect(s.pauseIntervals, pausesBefore);
          });
        }
      }
    }
  });

  test('table covers 5 valid and 11 invalid pairs', () {
    var valid = 0;
    for (final state in SessionState.values) {
      valid += RecordingSession.allowedEventsFor(state).length;
    }
    expect(valid, validTransitions.length);
    expect(SessionState.values.length * SessionEvent.values.length - valid, 11);
  });

  test('convenience methods match handle()', () {
    final s = RecordingSession(clock: FakeClock())..start();
    expect(s.state, SessionState.recording);
    s.pause();
    expect(s.state, SessionState.paused);
    s.resume();
    expect(s.state, SessionState.recording);
    s.stop();
    expect(s.state, SessionState.stopped);
    expect(s.pause, throwsA(isA<InvalidTransitionError>()));
  });

  test('error message lists allowed events, or none when stopped', () {
    expect(
      () => sessionIn(SessionState.recording).start(),
      throwsA(
        isA<InvalidTransitionError>().having(
          (e) => e.message,
          'message',
          'Cannot start a session that is recording. '
              'Allowed in recording: pause, stop.',
        ),
      ),
    );
    expect(
      () => sessionIn(SessionState.stopped).resume(),
      throwsA(
        isA<InvalidTransitionError>().having(
          (e) => e.message,
          'message',
          endsWith('Allowed in stopped: none.'),
        ),
      ),
    );
  });

  group('recorded time excludes pauses', () {
    late FakeClock clock;
    late RecordingSession s;

    setUp(() {
      clock = FakeClock()
        ..advance(const Duration(seconds: 100)); // non-zero origin
      s = RecordingSession(clock: clock);
    });

    test('idle session does not accumulate time', () {
      clock.advance(s1 * 5);
      expect(s.recordedDuration, Duration.zero);
    });

    test('grows while recording', () {
      s.start();
      clock.advance(s1 * 3);
      expect(s.recordedDuration, s1 * 3);
      expect(s.totalDuration, s1 * 3);
    });

    test('is frozen while paused; open pause counted in pausedDuration', () {
      s.start();
      clock.advance(s1 * 2);
      s.pause();
      clock.advance(s1 * 10);
      expect(s.recordedDuration, s1 * 2);
      expect(s.pausedDuration, s1 * 10);
      expect(s.totalDuration, s1 * 12);
    });

    test('multiple pauses are all excluded', () {
      s.start();
      clock.advance(s1 * 2); // rec 2
      s.pause();
      clock.advance(s1 * 5); // pause 5
      s.resume();
      clock.advance(s1 * 3); // rec 3
      s.pause();
      clock.advance(const Duration(milliseconds: 1500)); // pause 1.5
      s.resume();
      clock.advance(const Duration(milliseconds: 250)); // rec 0.25
      expect(s.recordedDuration, const Duration(milliseconds: 5250));
      expect(s.pausedDuration, const Duration(milliseconds: 6500));
    });

    test('is frozen after stop', () {
      s.start();
      clock.advance(s1 * 4);
      s.stop();
      clock.advance(s1 * 60);
      expect(s.recordedDuration, s1 * 4);
      expect(s.totalDuration, s1 * 4);
      expect(s.stoppedOffset, s1 * 4);
    });

    test('stop while paused closes the pause and excludes it', () {
      s.start();
      clock.advance(s1 * 2);
      s.pause();
      clock.advance(s1 * 7);
      s.stop();
      clock.advance(s1 * 30);
      expect(s.recordedDuration, s1 * 2);
      expect(s.pausedDuration, s1 * 7);
      expect(s.pauseIntervals, [PauseInterval(s1 * 2, s1 * 9)]);
    });
  });

  group('pause intervals', () {
    test('recorded as offsets from session start', () {
      final clock = FakeClock()..advance(s1 * 1000);
      final s = RecordingSession(clock: clock)..start();
      clock.advance(s1 * 2);
      s.pause();
      expect(s.pauseIntervals, [PauseInterval(s1 * 2)]);
      expect(s.pauseIntervals.single.isOpen, isTrue);

      clock.advance(s1 * 3);
      s.resume();
      clock.advance(s1 * 4);
      s.pause();
      clock.advance(s1);
      s.resume();
      clock.advance(s1);
      s.stop();

      expect(s.pauseIntervals, [
        PauseInterval(s1 * 2, s1 * 5),
        PauseInterval(s1 * 9, s1 * 10),
      ]);
      expect(s.pauseIntervals.every((p) => !p.isOpen), isTrue);
      expect(s.stoppedOffset, s1 * 11);
    });

    test('exposed list is unmodifiable', () {
      final s = sessionIn(SessionState.paused);
      expect(
        () => s.pauseIntervals.add(const PauseInterval(Duration.zero)),
        throwsUnsupportedError,
      );
    });
  });

  group('pause reasons', () {
    test('default reason is user; auto_background is kept', () {
      final clock = FakeClock();
      final s = RecordingSession(clock: clock)..start();
      clock.advance(s1);
      s.pause();
      expect(s.pauseReason, PauseReason.user);
      clock.advance(s1);
      s.resume();
      expect(s.pauseReason, isNull);
      clock.advance(s1);
      s.pause(PauseReason.autoBackground);
      expect(s.pauseReason, PauseReason.autoBackground);
      clock.advance(s1 * 2);
      s.stop();
      expect(s.pauseIntervals, [
        PauseInterval(s1, s1 * 2, PauseReason.user),
        PauseInterval(s1 * 3, s1 * 5, PauseReason.autoBackground),
      ]);
    });

    test('handle(pause) takes a reason', () {
      final s = sessionIn(SessionState.recording)
        ..handle(SessionEvent.pause, pauseReason: PauseReason.autoBackground);
      expect(s.pauseIntervals.single.reason, PauseReason.autoBackground);
      expect(s.pauseIntervals.single.isOpen, isTrue);
    });

    test('wire names for the manifest', () {
      expect(PauseReason.user.wireName, 'user');
      expect(PauseReason.autoBackground.wireName, 'auto_background');
    });

    test('reason is part of equality', () {
      expect(
        PauseInterval(s1, s1 * 2, PauseReason.user),
        isNot(PauseInterval(s1, s1 * 2, PauseReason.autoBackground)),
      );
    });
  });

  test('runStartOffset: zero for the first run, then each resume offset', () {
    final clock = FakeClock()..advance(s1 * 50);
    final s = RecordingSession(clock: clock);
    expect(s.runStartOffset, isNull);
    expect(s.runCount, 0);
    s.start();
    expect((s.runCount, s.runStartOffset), (1, Duration.zero));
    clock.advance(s1 * 2);
    s.pause();
    expect(s.runStartOffset, isNull);
    clock.advance(s1 * 3);
    s.resume();
    expect((s.runCount, s.runStartOffset), (2, s1 * 5));
    clock.advance(s1);
    s.pause();
    clock.advance(const Duration(milliseconds: 250));
    s.resume();
    expect(
      (s.runCount, s.runStartOffset),
      (3, const Duration(milliseconds: 6250)),
    );
    s.stop();
    expect(s.runStartOffset, isNull);
    expect(s.runCount, 3);
    expect(s.runs.map((r) => r.startOffset), [
      Duration.zero,
      s1 * 5,
      const Duration(milliseconds: 6250),
    ]);
  });

  test('per run: tap offset, startup delay and actual capture start', () {
    final clock = FakeClock();
    final s = RecordingSession(clock: clock)..start();
    expect(s.runs, [const RecordingRun(Duration.zero)]);
    s.setCaptureStart(
      0,
      delay: const Duration(milliseconds: 120),
      captureStartOffset: const Duration(milliseconds: 40),
    );
    clock.advance(s1);
    s.pause();
    clock.advance(s1);
    s.resume();
    expect(s.runs.last.captureStartDelay, isNull, reason: 'not measured yet');
    expect(s.runs.last.captureStartOffset, isNull);
    s.setCaptureStart(
      1,
      delay: const Duration(microseconds: 85500),
      captureStartOffset: const Duration(microseconds: 2005500),
    );
    s.stop();
    expect(s.runs, [
      const RecordingRun(
        Duration.zero,
        captureStartDelay: Duration(milliseconds: 120),
        captureStartOffset: Duration(milliseconds: 40),
      ),
      RecordingRun(
        s1 * 2,
        captureStartDelay: const Duration(microseconds: 85500),
        captureStartOffset: const Duration(microseconds: 2005500),
      ),
    ]);
    expect(
      () => s.setCaptureStart(
        2,
        delay: Duration.zero,
        captureStartOffset: Duration.zero,
      ),
      throwsRangeError,
    );
    expect(() => s.runs.clear(), throwsUnsupportedError);
  });

  test('offsetAt converts clock readings to session offsets', () {
    final clock = FakeClock()..advance(s1 * 100);
    final s = RecordingSession(clock: clock)..start();
    expect(s.offsetAt(clock.now() + s1 * 3), s1 * 3);
  });

  group('session ID and wall-clock start', () {
    final idPattern = RegExp(r'^\d{8}T\d{6}_[0-9a-f]{4}$');

    test('both are set at start from the wall clock, not at construction', () {
      var wall = DateTime(2026, 10, 15, 9, 0, 0);
      final s = RecordingSession(
        clock: FakeClock(),
        wallClock: () => wall,
        random: FakeRandom(0xbeef),
      );
      expect(s.id, isNull);
      expect(s.startWallClock, isNull);

      wall = DateTime(2026, 10, 15, 14, 23, 7, 456);
      s.start();
      expect(s.startWallClock, DateTime(2026, 10, 15, 14, 23, 7, 456));
      expect(s.startWallClock!.isUtc, isFalse, reason: 'local time');
      expect(s.id, '20261015T142307_beef');
      expect(s.id, matches(idPattern));
      expect(
        formatIso8601WithOffset(s.startWallClock!),
        startsWith('2026-10-15T14:23:07.456'),
      );

      // Later wall-clock readings do not change them.
      wall = DateTime(2030);
      s
        ..pause()
        ..resume()
        ..stop();
      expect(s.id, '20261015T142307_beef');
      expect(s.startWallClock, DateTime(2026, 10, 15, 14, 23, 7, 456));
    });

    test('defaults: DateTime.now and a secure random suffix', () {
      final before = DateTime.now();
      final s = RecordingSession(clock: FakeClock())..start();
      final after = DateTime.now();
      expect(s.id, matches(idPattern));
      expect(s.startWallClock!.isBefore(before), isFalse);
      expect(s.startWallClock!.isAfter(after), isFalse);
      expect(s.startWallClock!.isUtc, isFalse);
      expect(s.id, startsWith(formatCompactTimestamp(s.startWallClock!)));
    });

    test('wall-clock jumps do not affect recorded time', () {
      final clock = FakeClock();
      var wall = DateTime(2026, 10, 15, 12);
      final s = RecordingSession(clock: clock, wallClock: () => wall)..start();
      wall = wall.subtract(const Duration(hours: 1)); // e.g. manual change
      clock.advance(s1 * 10);
      expect(s.recordedDuration, s1 * 10);
    });
  });
}
