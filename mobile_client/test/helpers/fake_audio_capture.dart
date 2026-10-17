import 'dart:async';
import 'dart:typed_data';

import 'package:echo_vault/capture/audio_capture.dart';

import 'pcm.dart';

/// [AudioCapture] whose bytes are pushed by the test with [emit], at any
/// time, including while paused or stopped (to model late or misbehaving
/// platform delivery). Delivery is synchronous.
class FakeAudioCapture implements AudioCapture {
  final _pcm = StreamController<Uint8List>.broadcast(sync: true);

  /// Calls received, in order: start, pause, resume, stop.
  final List<String> calls = [];

  /// When set, the next call with this name waits for the completer.
  final Map<String, Completer<void>> gates = {};

  /// When set, the next call with this name throws it.
  final Map<String, Object> errors = {};

  /// True between start/resume and pause/stop.
  bool running = false;

  @override
  Stream<Uint8List> get pcm => _pcm.stream;

  void emit(Uint8List bytes) => _pcm.add(bytes);
  void emitSamples(List<int> samples) => emit(pcmBytes(samples));
  void fail(Object error) => _pcm.addError(error);

  @override
  Future<void> start() => _call('start', running: true);
  @override
  Future<void> pause() => _call('pause', running: false);
  @override
  Future<void> resume() => _call('resume', running: true);
  @override
  Future<void> stop() => _call('stop', running: false);

  Future<void> _call(String name, {required bool running}) async {
    calls.add(name);
    if (gates.remove(name) case final gate?) await gate.future;
    if (errors.remove(name) case final error?) throw error;
    this.running = running;
  }
}
