import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

import 'audio_capture.dart';

/// [AudioCapture] backed by the `record` plugin's PCM stream.
///
/// [pause] stops the plugin's recorder (releasing the microphone) and
/// [resume] starts a new stream, instead of using the plugin's own
/// pause/resume: for streams that only stops *reading*, while Android's
/// AudioRecord keeps the microphone open and buffers audio from the paused
/// period, which would then be delivered after resume (FR2).
///
/// Permission is not requested here; the app's MethodChannel does that
/// before [start].
class RecordAudioCapture implements AudioCapture {
  RecordAudioCapture({AudioRecorder Function()? recorderFactory, this.log})
    : _recorderFactory = recorderFactory ?? AudioRecorder.new;

  /// 16 kHz mono PCM16, with the platform's auto gain, echo cancellation and
  /// noise suppression explicitly off.
  ///
  /// - `audioInterruption: none`: the plugin must not pause capture on its
  ///   own (e.g. on audio-focus loss); only the session decides, so the
  ///   session timeline and the audio stay in step. It also means the plugin
  ///   does not request audio focus.
  /// - `manageBluetooth: false`: no Bluetooth SCO routing, so the input does
  ///   not switch to a headset mic (and start/resume do not wait up to 2.5 s
  ///   for SCO).
  static const config = RecordConfig(
    encoder: AudioEncoder.pcm16bits,
    sampleRate: kSampleRate,
    numChannels: kChannels,
    autoGain: false,
    echoCancel: false,
    noiseSuppress: false,
    audioInterruption: AudioInterruptionMode.none,
    androidConfig: AndroidRecordConfig(manageBluetooth: false),
  );

  final AudioRecorder Function() _recorderFactory;
  final void Function(String message)? log;

  final _pcm = StreamController<Uint8List>.broadcast();
  AudioRecorder? _recorder;
  StreamSubscription<Uint8List>? _native;

  @override
  Stream<Uint8List> get pcm => _pcm.stream;

  @override
  Future<void> start() => _startNative();

  @override
  Future<void> pause() => _stopNative();

  @override
  Future<void> resume() => _startNative();

  @override
  Future<void> stop() => _stopNative();

  /// Releases the plugin's recorder. The capture cannot be used afterwards.
  Future<void> dispose() async {
    await _stopNative();
    await _recorder?.dispose();
    _recorder = null;
    await _pcm.close();
  }

  AudioRecorder _ensureRecorder() {
    if (_recorder case final r?) return r;
    final r = _recorderFactory();
    unawaited(r.setOnConfigChanged(_onConfigChanged));
    return _recorder = r;
  }

  Future<void> _startNative() async {
    if (_native != null) return;
    final stream = await _ensureRecorder().startStream(config);
    late final StreamSubscription<Uint8List> sub;
    sub = stream.listen(
      _pcm.add,
      onError: _pcm.addError,
      onDone: () {
        // Expected after _stopNative (which clears _native first).
        if (!identical(_native, sub)) return;
        _native = null;
        _fail('the microphone stream ended unexpectedly');
      },
    );
    _native = sub;
  }

  Future<void> _stopNative() async {
    final sub = _native;
    if (sub == null) return;
    _native = null;
    await _recorder?.stop();
    await sub.cancel();
  }

  /// The plugin adjusted the requested config to the hardware. Anything but
  /// 16 kHz mono PCM16 would corrupt every frame downstream, so it is
  /// reported as a capture failure.
  void _onConfigChanged(RecordConfig actual) {
    log?.call('[capture] platform changed the config: $actual');
    if (actual.sampleRate != kSampleRate ||
        actual.numChannels != kChannels ||
        actual.encoder != AudioEncoder.pcm16bits) {
      _fail(
        'unsupported capture format: ${actual.encoder.name}, '
        '${actual.sampleRate} Hz, ${actual.numChannels} ch',
      );
    }
  }

  void _fail(String message) {
    log?.call('[capture] $message');
    if (!_pcm.isClosed) _pcm.addError(CaptureFailure(message));
  }
}
