import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

import 'theme/ember_theme.dart';

/// The background photo used by Home and the Recording screen. Replace the
/// file to change it.
const kBackgroundImage = 'assets/backgrounds/home_background.jpg';

/// Home's looping background video. Optional: while the file is missing
/// (or cannot be played) the photo is shown instead.
const kBackgroundVideo = 'assets/backgrounds/home_background.mp4';

/// The immersive back layers of Home and the Recording screen, back to
/// front: the photo (and, when [videoAsset] is set and present, a muted
/// looping video over it), blurred; a dark-red glass tint; black fades at
/// the top and bottom; a vignette.
///
/// The video plays only while [playing] is true and this screen is visible
/// (not covered by another page); it is muted, does not take audio focus
/// and pauses with the app.
class ImmersiveBackdrop extends StatefulWidget {
  const ImmersiveBackdrop({
    super.key,
    this.imageAsset = kBackgroundImage,
    this.videoAsset,
    this.playing = true,
    this.blur = 10,
  });

  final String imageAsset;
  final String? videoAsset;
  final bool playing;

  /// Blur of the glass layer over the photo/video (logical pixels).
  final double blur;

  static const imageKey = Key('backdrop-image');
  static const videoKey = Key('backdrop-video');

  @override
  State<ImmersiveBackdrop> createState() => _ImmersiveBackdropState();
}

class _ImmersiveBackdropState extends State<ImmersiveBackdrop> {
  VideoPlayerController? _video;
  bool _videoReady = false;
  bool _onScreen = true;
  bool _disposed = false;

  @override
  void initState() {
    super.initState();
    final asset = widget.videoAsset;
    if (asset != null) unawaited(_loadVideo(asset));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // False while another page covers this one.
    final onScreen = TickerMode.of(context);
    if (onScreen != _onScreen) {
      _onScreen = onScreen;
      _syncPlayback();
    }
  }

  @override
  void didUpdateWidget(ImmersiveBackdrop old) {
    super.didUpdateWidget(old);
    if (old.playing != widget.playing) _syncPlayback();
  }

  /// Loads the video only if the file is in the app (no error otherwise).
  Future<void> _loadVideo(String asset) async {
    try {
      final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
      if (_disposed) return;
      if (!manifest.listAssets().contains(asset)) {
        if (kDebugMode) debugPrint('[backdrop] no $asset in the app: photo');
        return;
      }
      final controller = VideoPlayerController.asset(
        asset,
        videoPlayerOptions: VideoPlayerOptions(mixWithOthers: true),
      );
      _video = controller;
      await controller.initialize();
      await controller.setLooping(true);
      await controller.setVolume(0);
      if (_disposed) return;
      setState(() => _videoReady = true);
      _syncPlayback();
    } catch (e) {
      // Keep the photo. Usual cause: a video the phone cannot decode (e.g.
      // 4K); use H.264, 1080p or smaller.
      if (kDebugMode) debugPrint('[backdrop] video unavailable, photo: $e');
      final failed = _video;
      _video = null;
      if (failed != null) unawaited(failed.dispose());
      if (!_disposed && mounted) setState(() => _videoReady = false);
    }
  }

  void _syncPlayback() {
    final video = _video;
    if (video == null || !_videoReady) return;
    final play = widget.playing && _onScreen;
    if (play && !video.value.isPlaying) {
      unawaited(video.play());
    } else if (!play && video.value.isPlaying) {
      unawaited(video.pause());
    }
  }

  @override
  void dispose() {
    _disposed = true;
    final video = _video;
    _video = null;
    if (video != null) unawaited(video.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final video = _video;
    final blur = widget.blur;
    return ExcludeSemantics(
      child: RepaintBoundary(
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Fallback colour while the photo loads (or if it is missing).
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0, -0.2),
                  radius: 1.1,
                  colors: [EvEmber.wine, EvEmber.deep, EvEmber.black],
                  stops: [0, 0.55, 1],
                ),
              ),
            ),
            // 1. The photo (and video), far back, blurred.
            ImageFiltered(
              imageFilter: ui.ImageFilter.blur(
                sigmaX: blur,
                sigmaY: blur,
                tileMode: TileMode.decal,
              ),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Image.asset(
                    widget.imageAsset,
                    key: ImmersiveBackdrop.imageKey,
                    fit: BoxFit.cover,
                    alignment: const Alignment(0, -0.1),
                    filterQuality: FilterQuality.medium,
                    errorBuilder: (_, _, _) => const SizedBox.shrink(),
                  ),
                  if (video != null)
                    AnimatedOpacity(
                      opacity: _videoReady ? 1 : 0,
                      duration: const Duration(milliseconds: 600),
                      child: _videoReady
                          ? FittedBox(
                              key: ImmersiveBackdrop.videoKey,
                              fit: BoxFit.cover,
                              clipBehavior: Clip.hardEdge,
                              child: SizedBox(
                                width: video.value.size.width,
                                height: video.value.size.height,
                                child: VideoPlayer(video),
                              ),
                            )
                          : const SizedBox.shrink(),
                    ),
                ],
              ),
            ),
            // 2. The glass: a translucent dark-red tint over the blur.
            const ColoredBox(color: Color(0x40160606)),
            // 3. Depth: black at the top and bottom, the picture glowing
            //    through in the middle.
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0xB3070304),
                    Color(0x10070304),
                    Color(0x26070304),
                    Color(0xE6070304),
                  ],
                  stops: [0, 0.3, 0.62, 1],
                ),
              ),
            ),
            // 4. Vignette towards the edges.
            const DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0, -0.1),
                  radius: 1.15,
                  colors: [Color(0x00000000), Color(0x99000000)],
                  stops: [0.55, 1],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
