import 'package:flutter/material.dart';

import 'components.dart';
import 'processing_privacy_screen.dart';
import 'theme/app_theme.dart';

/// Assistant: asking questions about past conversations. The assistant runs
/// on the PC and is not connected to this app yet, so the composer is
/// disabled with the reason shown, and no answers are ever generated here.
class AssistantScreen extends StatelessWidget {
  const AssistantScreen({super.key});

  static const composerKey = Key('assistant-composer');
  static const unavailableMessage =
      'The assistant isn’t connected to this app yet';

  static const _examples = [
    'What did we agree on in yesterday’s meeting?',
    'When is the project deadline we discussed?',
    'Summarise my conversations from this week.',
  ];

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Assistant'), centerTitle: false),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(
                  EvSpace.md,
                  EvSpace.lg,
                  EvSpace.md,
                  EvSpace.lg,
                ),
                children: [
                  const Center(
                    child: IconBadge(
                      Icons.auto_awesome_outlined,
                      color: EvColors.teal,
                      size: 72,
                    ),
                  ),
                  const SizedBox(height: EvSpace.lg),
                  Text(
                    'Ask about your conversations',
                    style: textTheme.headlineSmall,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: EvSpace.xs),
                  Text(
                    'The Echo Vault assistant answers questions using what '
                    'it has learned from your recordings. It runs on your '
                    'own PC, not in the cloud.',
                    style: textTheme.bodyMedium?.copyWith(
                      color: EvColors.textMuted,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SectionTitle('Questions you’ll be able to ask'),
                  for (final example in _examples) ...[
                    _ExamplePrompt(text: example),
                    const SizedBox(height: EvSpace.sm),
                  ],
                  const SizedBox(height: EvSpace.xs),
                  Center(
                    child: TextButton(
                      onPressed: () => Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const ProcessingPrivacyScreen(),
                        ),
                      ),
                      child: const Text('What works today'),
                    ),
                  ),
                ],
              ),
            ),
            const _DisabledComposer(),
          ],
        ),
      ),
    );
  }
}

/// An example question (not tappable: there is nothing to send it to).
class _ExamplePrompt extends StatelessWidget {
  const _ExamplePrompt({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return EvCard(
      padding: const EdgeInsets.symmetric(
        horizontal: EvSpace.md,
        vertical: EvSpace.sm + 2,
      ),
      child: Row(
        children: [
          const Icon(
            Icons.chat_bubble_outline_rounded,
            size: 18,
            color: EvColors.textSubtle,
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Text(
              text,
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
            ),
          ),
        ],
      ),
    );
  }
}

/// The message box, shown disabled with the reason.
class _DisabledComposer extends StatelessWidget {
  const _DisabledComposer();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Container(
      key: AssistantScreen.composerKey,
      padding: const EdgeInsets.fromLTRB(
        EvSpace.md,
        EvSpace.sm,
        EvSpace.md,
        EvSpace.md,
      ),
      decoration: const BoxDecoration(
        color: EvColors.surfaceLow,
        border: Border(top: BorderSide(color: EvColors.border)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: EvSpace.md,
                    vertical: EvSpace.sm + 2,
                  ),
                  decoration: BoxDecoration(
                    color: EvColors.surface,
                    borderRadius: BorderRadius.circular(EvRadius.pill),
                    border: Border.all(color: EvColors.border),
                  ),
                  child: Text(
                    'Ask a question…',
                    style: textTheme.bodyMedium?.copyWith(
                      color: EvColors.textSubtle,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: EvSpace.xs),
              const IconButton.filled(
                onPressed: null,
                tooltip: 'Send (not available yet)',
                icon: Icon(Icons.arrow_upward_rounded),
              ),
            ],
          ),
          const SizedBox(height: EvSpace.xs),
          Row(
            children: [
              const Icon(
                Icons.lock_clock_outlined,
                size: 14,
                color: EvColors.textSubtle,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  AssistantScreen.unavailableMessage,
                  style: textTheme.bodySmall?.copyWith(
                    color: EvColors.textSubtle,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
