import 'package:flutter/material.dart';

import 'components.dart';
import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// First-run welcome: three short pages on what Echo Vault does, with Skip
/// and Get started. Calls [onDone] when the user leaves it.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, required this.onDone});

  final VoidCallback onDone;

  static const skipKey = Key('onboarding-skip');
  static const nextKey = Key('onboarding-next');

  static const _pages = [
    _Benefit(
      icon: Icons.mic_none_rounded,
      color: EvEmber.accentSoft,
      title: 'Capture naturally',
      body:
          'Record a conversation only when you choose. You start, pause and '
          'stop every session yourself; Echo Vault never listens in the '
          'background.',
    ),
    _Benefit(
      icon: Icons.hub_outlined,
      color: Colors.white,
      title: 'Connect knowledge',
      body:
          'Your recordings go to Echo Vault on your own PC, which turns '
          'speech into text. Linking people, topics and dates is on the '
          'way.',
    ),
    _Benefit(
      icon: Icons.shield_outlined,
      color: EvEmber.accentSoft,
      title: 'Keep control',
      body:
          'Speech detection runs on this phone, and recordings travel only '
          'over your local network to your own PC. No cloud services, no '
          'analytics.',
    ),
  ];

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _pager = PageController();
  int _index = 0;

  bool get _last => _index == OnboardingScreen._pages.length - 1;

  @override
  void dispose() {
    _pager.dispose();
    super.dispose();
  }

  void _next() {
    if (_last) {
      widget.onDone();
      return;
    }
    final target = _index + 1;
    if (EvMotion.reduced(context)) {
      _pager.jumpToPage(target);
    } else {
      _pager.animateToPage(
        target,
        duration: EvMotion.medium,
        curve: EvMotion.curve,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return EmberPage(
      child: Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                EvSpace.lg,
                EvSpace.md,
                EvSpace.xs,
                0,
              ),
              child: Row(
                children: [
                  const Flexible(child: BrandLogo(height: 34)),
                  const Spacer(),
                  AnimatedOpacity(
                    opacity: _last ? 0 : 1,
                    duration: EvMotion.fast,
                    child: TextButton(
                      key: OnboardingScreen.skipKey,
                      onPressed: _last ? null : widget.onDone,
                      style: TextButton.styleFrom(
                        foregroundColor: EvEmber.textSoft,
                      ),
                      child: const Text('Skip'),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: PageView(
                controller: _pager,
                onPageChanged: (i) => setState(() => _index = i),
                children: [
                  for (final page in OnboardingScreen._pages)
                    _BenefitPage(benefit: page),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                EvSpace.lg,
                0,
                EvSpace.lg,
                EvSpace.lg,
              ),
              child: Column(
                children: [
                  _Dots(count: OnboardingScreen._pages.length, index: _index),
                  const SizedBox(height: EvSpace.lg),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      key: OnboardingScreen.nextKey,
                      onPressed: _next,
                      child: Text(_last ? 'Get started' : 'Continue'),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    ),
    );
  }
}

class _Benefit {
  const _Benefit({
    required this.icon,
    required this.color,
    required this.title,
    required this.body,
  });

  final IconData icon;
  final Color color;
  final String title;
  final String body;
}

class _BenefitPage extends StatelessWidget {
  const _BenefitPage({required this.benefit});

  final _Benefit benefit;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return LayoutBuilder(
      builder: (context, box) => SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: EvSpace.lg),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: box.maxHeight),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _BenefitArt(icon: benefit.icon, color: benefit.color),
              const SizedBox(height: EvSpace.xl),
              Text(benefit.title, style: textTheme.headlineMedium),
              const SizedBox(height: EvSpace.sm),
              Text(
                benefit.body,
                style: textTheme.bodyLarge?.copyWith(
                  color: EvEmber.textSoft,
                  height: 1.5,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Quiet illustration: concentric rings around the benefit icon.
class _BenefitArt extends StatelessWidget {
  const _BenefitArt({required this.icon, required this.color});

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    Widget ring(double size, double alpha) => Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: color.withValues(alpha: alpha)),
      ),
    );
    return SizedBox(
      width: 132,
      height: 132,
      child: Stack(
        alignment: Alignment.center,
        children: [
          ring(132, 0.12),
          ring(100, 0.22),
          Container(
            width: 68,
            height: 68,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.14),
            ),
            child: Icon(icon, size: 32, color: color),
          ),
        ],
      ),
    );
  }
}

class _Dots extends StatelessWidget {
  const _Dots({required this.count, required this.index});

  final int count;
  final int index;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Page ${index + 1} of $count',
      excludeSemantics: true,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          for (var i = 0; i < count; i++)
            AnimatedContainer(
              duration: EvMotion.fast,
              margin: const EdgeInsets.symmetric(horizontal: 3),
              width: i == index ? 22 : 7,
              height: 7,
              decoration: BoxDecoration(
                color: i == index ? Colors.white : EvEmber.glassBorder,
                borderRadius: BorderRadius.circular(EvRadius.pill),
              ),
            ),
        ],
      ),
    );
  }
}
