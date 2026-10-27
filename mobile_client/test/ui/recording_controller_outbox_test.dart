import 'dart:convert';
import 'dart:io';

import 'package:echo_vault/transfer/chunk_files.dart';
import 'package:echo_vault/transfer/chunk_pipeline.dart';
import 'package:echo_vault/ui/recording_controller.dart';
import 'package:flutter_test/flutter_test.dart';

import '../helpers/fake_audio_capture.dart';
import '../helpers/fake_clock.dart';
import '../helpers/fake_lifecycle.dart';
import '../helpers/fake_microphone_permission.dart';
import '../helpers/fake_opus_encoder.dart';
import '../helpers/fake_random.dart';
import '../helpers/fake_screen_awake.dart';
import '../helpers/signals.dart';

/// End to end through the controller: capture → frames → segments → the
/// chunk pipeline → outbox, with a fake encoder and a temp `files/`.
void main() {
  late Directory files;
  late FakeClock clock;
  late FakeAudioCapture capture;
  late FakeOpusEncoder encoder;
  late List<String> published;
  late RecordingController controller;

  setUp(() {
    files = Directory.systemTemp.createTempSync('echo_vault_outbox');
    clock = FakeClock();
    capture = FakeAudioCapture();
    encoder = FakeOpusEncoder();
    published = [];
    controller = RecordingController(
      permission: FakeMicrophonePermission(),
      capture: capture,
      screenAwake: FakeScreenAwake(),
      lifecycle: FakeLifecycle(),
      clock: clock,
      wallClock: () => DateTime(2026, 10, 18, 11, 0, 0),
      random: FakeRandom(0xbeef),
      chunkPipelineFactory: (session) => ChunkPipeline(
        sessionId: session.id!,
        encoder: encoder,
        filesDir: Future.value(files.path),
        appVersion: Future.value('1.0.0+1'),
        onPublished: published.add,
      ),
      tickInterval: const Duration(hours: 1),
    );
  });

  tearDown(() {
    controller.dispose();
    files.deleteSync(recursive: true);
  });

  test('every segment becomes .opus + .json in the outbox; the manifest '
      'comes last and matches', () async {
    const sid = '20261018T110000_beef';
    await controller.start();
    await pumpEventQueue();
    capture.emitSamples(silence(20) + tone(31) + silence(25)); // segment 0
    controller.pause(); // user pause
    clock.advance(const Duration(seconds: 2));
    controller.resume();
    await pumpEventQueue();
    clock.advance(const Duration(milliseconds: 400));
    capture.emitSamples(tone(40) + silence(25)); // segment 1
    controller.stop();

    final manifest = await controller.chunkPipeline!.manifest;
    expect(controller.segmentCount, 2);
    expect(published, [
      '${sid}_00000.opus',
      '${sid}_00000.json',
      '${sid}_00001.opus',
      '${sid}_00001.json',
      '${sid}_manifest.json',
    ]);
    expect(manifest['chunk_count'], 2);
    expect(manifest['seqs'], [0, 1]);
    expect(
      (manifest['pause_intervals']! as List).single,
      containsPair('reason', 'user'),
    );
    final runs = (manifest['runs']! as List).cast<Map<String, Object?>>();
    expect(runs, hasLength(2));
    expect(runs[1]['startup_delay_ms'], 400.0);

    final dir = OutboxLayout(files.path).sessionDir(sid);
    final sidecar1 =
        jsonDecode(File('$dir/${sid}_00001.json').readAsStringSync()) as Map;
    expect(sidecar1['run'], 1);
    expect(sidecar1['run_startup_delay_ms'], 400.0);
    expect(sidecar1['run_tap_offset_ms'], runs[1]['tap_offset_ms']);
    final acc = manifest['frame_accounting']! as Map;
    expect(acc['balanced'], isTrue);
    expect(acc['segments_emitted'], 2);
  });
}
