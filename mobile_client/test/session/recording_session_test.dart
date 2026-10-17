import 'package:echo_vault/session/recording_session.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_clock.dart';

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
}
