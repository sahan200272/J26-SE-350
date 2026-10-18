import 'dart:async';

import 'package:flutter/material.dart';

import 'components.dart';
import 'theme/app_theme.dart';

/// Short branded launch screen. Continues the native launch window (same
/// navy background and centred symbol), then calls [onFinished]. A tap
/// skips it; with reduced motion it shows without animation.
class SplashScreen extends StatefulWidget {
  const SplashScreen({
    super.key,
    required this.onFinished,
    this.duration = const Duration(milliseconds: 1500),
  });

  final VoidCallback onFinished;
  final Duration duration;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );
  Timer? _timer;
  bool _done = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_timer != null) return;
    if (EvMotion.reduced(context)) {
      _controller.value = 1;
    } else {
      _controller.forward();
    }
    _timer = Timer(widget.duration, _finish);
  }

  void _finish() {
    if (_done || !mounted) return;
    _done = true;
    _timer?.cancel();
    widget.onFinished();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final symbol = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0, 0.7, curve: Curves.easeOutCubic),
    );
    final text = CurvedAnimation(
      parent: _controller,
      curve: const Interval(0.35, 1, curve: Curves.easeOut),
    );
    return Scaffold(
      backgroundColor: EvColors.navy,
      body: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: _finish,
        child: SafeArea(
          child: Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: EvSpace.lg),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FadeTransition(
                    opacity: symbol,
                    child: ScaleTransition(
                      scale: Tween(begin: 0.9, end: 1.0).animate(symbol),
                      child: const BrandSymbol(
                        size: 112,
                        semanticLabel: 'Echo Vault',
                      ),
                    ),
                  ),
                  const SizedBox(height: EvSpace.lg),
                  FadeTransition(
                    opacity: text,
                    child: SlideTransition(
                      position: Tween(
                        begin: const Offset(0, 0.15),
                        end: Offset.zero,
                      ).animate(text),
                      child: Column(
                        children: [
                          Text(
                            'Echo Vault',
                            textAlign: TextAlign.center,
                            style: textTheme.headlineMedium?.copyWith(
                              color: EvColors.snow,
                            ),
                          ),
                          const SizedBox(height: EvSpace.xs),
                          Text(
                            EvBrand.tagline,
                            textAlign: TextAlign.center,
                            style: textTheme.bodyMedium?.copyWith(
                              color: EvColors.textMuted,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
