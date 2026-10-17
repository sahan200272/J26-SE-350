import 'dart:async';
import 'dart:typed_data';

import 'package:echo_vault/capture/audio_capture.dart';
import 'package:echo_vault/capture/record_audio_capture.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:record/record.dart';

/// Stands in for the record plugin's platform side. Only the calls used by
/// [RecordAudioCapture] are implemented.
class FakeRecordPlatform extends RecordPlatform {
  final List<String> calls = [];
  final List<RecordConfig> configs = [];
  StreamController<Uint8List>? native;
  void Function(RecordConfig config)? configHandler;
  final _states = StreamController<RecordState>.broadcast();

  @override
  Future<void> create(String recorderId) async => calls.add('create');

  @override
  Future<Stream<Uint8List>> startStream(
    String recorderId,
    RecordConfig config,
  ) async {
    calls.add('startStream');
    configs.add(config);
    native = StreamController<Uint8List>();
    return native!.stream;
  }

  @override
  Future<String?> stop(String recorderId) async {
    calls.add('stop');
    return null;
  }

  @override
  Future<void> pause(String recorderId) async => calls.add('pause');

  @override
  Future<void> resume(String recorderId) async => calls.add('resume');

  @override
  Future<void> dispose(String recorderId) async => calls.add('dispose');

  @override
  Stream<RecordState> onStateChanged(String recorderId) => _states.stream;

  @override
  void setOnConfigChanged(
    String recorderId,
    void Function(RecordConfig config)? handler,
  ) => configHandler = handler;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  late FakeRecordPlatform platform;
  late RecordAudioCapture capture;
  late List<Uint8List> received;
  late List<Object> errors;

  setUp(() {
    platform = FakeRecordPlatform();
    RecordPlatform.instance = platform;
    capture = RecordAudioCapture();
    received = [];
    errors = [];
    capture.pcm.listen(received.add, onError: errors.add);
  });

  Uint8List bytes(List<int> b) => Uint8List.fromList(b);

  test('requests 16 kHz mono PCM16 with AGC, AEC and NS explicitly off', () {
    const c = RecordAudioCapture.config;
    expect(c.encoder, AudioEncoder.pcm16bits);
    expect(c.sampleRate, 16000);
    expect(c.numChannels, 1);
    expect(c.autoGain, isFalse);
    expect(c.echoCancel, isFalse);
    expect(c.noiseSuppress, isFalse);
    expect(c.audioInterruption, AudioInterruptionMode.none);
    expect(c.androidConfig.manageBluetooth, isFalse);
  });

  test('no platform calls until start', () async {
    await pumpEventQueue();
    expect(platform.calls, isEmpty);
  });

  test(
    'start opens a stream with that config and forwards its bytes',
    () async {
      await capture.start();
      expect(platform.calls, ['create', 'startStream']);
      expect(
        platform.configs.single.toMap(),
        RecordAudioCapture.config.toMap(),
      );

      platform.native!
        ..add(bytes([1, 2, 3]))
        ..add(bytes([4]));
      await pumpEventQueue();
      expect(received, [
        bytes([1, 2, 3]),
        bytes([4]),
      ]);
    },
  );

  test('pause stops the recorder (mic released); resume starts a new '
      'stream; the plugin pause/resume is never used', () async {
    await capture.start();
    final first = platform.native!;
    await capture.pause();
    expect(platform.calls, ['create', 'startStream', 'stop']);

    // The old native stream is no longer forwarded.
    first.add(bytes([9, 9]));
    await pumpEventQueue();
    expect(received, isEmpty);

    await capture.resume();
    expect(platform.calls, ['create', 'startStream', 'stop', 'startStream']);
    platform.native!.add(bytes([5, 6]));
    await pumpEventQueue();
    expect(received, [
      bytes([5, 6]),
    ]);

    await capture.stop();
    expect(platform.calls.where((c) => c == 'pause' || c == 'resume'), isEmpty);
    expect(errors, isEmpty);
  });

  test('pause/stop when not running are no-ops', () async {
    await capture.pause();
    await capture.stop();
    await capture.start();
    await capture.stop();
    await capture.stop();
    expect(platform.calls, ['create', 'startStream', 'stop']);
  });

  test('a changed sample rate or channel count is a capture failure', () async {
    await capture.start();
    await pumpEventQueue();
    platform.configHandler!(RecordAudioCapture.config);
    await pumpEventQueue();
    expect(errors, isEmpty, reason: 'unchanged format is fine');

    platform.configHandler!(
      RecordAudioCapture.config.copyWith(sampleRate: 48000),
    );
    await pumpEventQueue();
    expect(
      errors.single,
      isA<CaptureFailure>().having(
        (e) => e.message,
        'message',
        contains('48000 Hz'),
      ),
    );
  });

  test(
    'the platform ending the stream on its own is a capture failure',
    () async {
      await capture.start();
      await platform.native!.close();
      await pumpEventQueue();
      expect(errors.single, isA<CaptureFailure>());
    },
  );

  test('platform errors are forwarded', () async {
    await capture.start();
    platform.native!.addError(Exception('read failed'));
    await pumpEventQueue();
    expect(errors.single.toString(), contains('read failed'));
  });

  test('dispose releases the recorder', () async {
    await capture.start();
    await capture.dispose();
    expect(platform.calls, ['create', 'startStream', 'stop', 'dispose']);
  });
}
