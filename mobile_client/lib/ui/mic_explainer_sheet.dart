import 'package:flutter/material.dart';

import 'theme/app_theme.dart';
import 'theme/ember_theme.dart';

/// Shown once, the first time the user taps the microphone: when and why
/// the microphone is used, before Android's own permission dialog.
///
/// Returns true for Continue (go on to the recording screen), false for
/// Not now or when the sheet is dismissed.
Future<bool> showMicExplainerSheet(BuildContext context) async {
  final go = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    // No slide-in with reduced motion.
    sheetAnimationStyle: EvMotion.reduced(context)
        ? AnimationStyle.noAnimation
        : null,
    useSafeArea: true,
    backgroundColor: const Color(0xFF170707),
    barrierColor: Colors.black.withValues(alpha: 0.6),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    ),
    clipBehavior: Clip.antiAlias,
    builder: (_) => const EmberScope(child: MicExplainerSheet()),
  );
  return go ?? false;
}

/// The sheet's content (public so it can be tested on its own).
class MicExplainerSheet extends StatelessWidget {
  const MicExplainerSheet({super.key});

  static const sheetKey = Key('mic-explainer');
  static const continueKey = Key('mic-explainer-continue');
  static const notNowKey = Key('mic-explainer-not-now');

  static const title = 'Before you record';

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return SingleChildScrollView(
      key: sheetKey,
      padding: EdgeInsets.fromLTRB(
        EvSpace.lg,
        EvSpace.sm,
        EvSpace.lg,
        EvSpace.lg + MediaQuery.paddingOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(
            child: Container(
              width: 36,
              height: 4,
              decoration: BoxDecoration(
                color: EvEmber.glassBorder,
                borderRadius: BorderRadius.circular(EvRadius.pill),
              ),
            ),
          ),
          const SizedBox(height: EvSpace.lg),
          Semantics(
            header: true,
            child: Text(
              title,
              style: textTheme.headlineSmall?.copyWith(color: Colors.white),
            ),
          ),
          const SizedBox(height: EvSpace.xs),
          Text(
            'How Echo Vault uses the microphone.',
            style: textTheme.bodyMedium?.copyWith(color: EvEmber.textSoft),
          ),
          const SizedBox(height: EvSpace.lg),
          const _Point(
            icon: Icons.mic_none_rounded,
            text:
                'Only while you record. You start, pause and stop it, and a '
                'red dot shows while it is on.',
          ),
          const _Point(
            icon: Icons.pause_circle_outline_rounded,
            text:
                'If you leave the app, recording pauses by itself. Nothing '
                'is recorded while paused.',
          ),
          const _Point(
            icon: Icons.shield_outlined,
            text:
                'Recordings stay on this phone until they go to your own PC '
                'over your local network. No cloud.',
          ),
          const _Point(
            icon: Icons.info_outline_rounded,
            text:
                'If Android asks for microphone access, choose “While using '
                'the app” or “Allow”.',
          ),
          const SizedBox(height: EvSpace.md),
          FilledButton(
            key: continueKey,
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Continue'),
          ),
          const SizedBox(height: EvSpace.xs),
          TextButton(
            key: notNowKey,
            onPressed: () => Navigator.of(context).pop(false),
            style: TextButton.styleFrom(
              foregroundColor: EvEmber.textSoft,
              minimumSize: const Size.fromHeight(48),
            ),
            child: const Text('Not now'),
          ),
        ],
      ),
    );
  }
}

class _Point extends StatelessWidget {
  const _Point({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: EvSpace.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              color: EvEmber.glassStrong,
            ),
            child: Icon(icon, size: 18, color: Colors.white),
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 7),
              child: Text(
                text,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Colors.white,
                  height: 1.4,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
