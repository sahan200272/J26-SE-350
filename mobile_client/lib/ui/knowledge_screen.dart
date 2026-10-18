import 'package:flutter/material.dart';

import 'components.dart';
import 'processing_privacy_screen.dart';
import 'theme/app_theme.dart';

/// Knowledge: where people, topics and their connections will be browsed.
/// The knowledge graph is built on the PC and is not connected to this app
/// yet, so this screen explains that instead of showing sample data.
class KnowledgeScreen extends StatelessWidget {
  const KnowledgeScreen({super.key, this.onStartRecording});

  final VoidCallback? onStartRecording;

  static const unavailableKey = Key('knowledge-unavailable');

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Knowledge'), centerTitle: false),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.md,
            EvSpace.md,
            EvSpace.xl,
          ),
          children: [
            const Center(child: _GraphArt()),
            const SizedBox(height: EvSpace.lg),
            Text(
              'Your connected knowledge',
              style: textTheme.headlineSmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: EvSpace.xs),
            Text(
              'Echo Vault links the people, organisations, places and dates '
              'that come up in your conversations, so you can see how they '
              'relate.',
              style: textTheme.bodyMedium?.copyWith(color: EvColors.textMuted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: EvSpace.lg),
            const NoticeCard(
              key: unavailableKey,
              icon: Icons.info_outline_rounded,
              title: 'Not available on this phone yet',
              message:
                  'Your knowledge is built on your PC. Browsing it from this '
                  'app is planned but not connected yet, so nothing is shown '
                  'here.',
              tone: PillTone.indigo,
            ),
            const SectionTitle('What you’ll find here'),
            const GroupCard(
              children: [
                InfoRow(
                  icon: Icons.person_outline_rounded,
                  iconColor: EvColors.indigo,
                  title: 'People',
                  subtitle: 'Who you talked with, and about',
                ),
                InfoRow(
                  icon: Icons.apartment_rounded,
                  iconColor: EvColors.indigo,
                  title: 'Organisations and places',
                  subtitle: 'Mentioned across your conversations',
                ),
                InfoRow(
                  icon: Icons.event_outlined,
                  iconColor: EvColors.indigo,
                  title: 'Dates and plans',
                  subtitle: 'Deadlines and events that came up',
                ),
              ],
            ),
            const SizedBox(height: EvSpace.lg),
            if (onStartRecording != null)
              FilledButton.icon(
                onPressed: onStartRecording,
                icon: const Icon(Icons.mic_rounded),
                label: const Text('Record a conversation'),
              ),
            const SizedBox(height: EvSpace.xs),
            TextButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => const ProcessingPrivacyScreen(),
                ),
              ),
              child: const Text('How processing works'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Quiet illustration: a few connected nodes.
class _GraphArt extends StatelessWidget {
  const _GraphArt();

  @override
  Widget build(BuildContext context) {
    return const ExcludeSemantics(
      child: SizedBox(
        width: 180,
        height: 120,
        child: CustomPaint(painter: _GraphPainter()),
      ),
    );
  }
}

class _GraphPainter extends CustomPainter {
  const _GraphPainter();

  static const _nodes = [
    Offset(0.50, 0.50),
    Offset(0.15, 0.25),
    Offset(0.85, 0.22),
    Offset(0.20, 0.82),
    Offset(0.82, 0.80),
    Offset(0.50, 0.08),
  ];
  static const _edges = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 5), (2, 5), (3, 4)];

  @override
  void paint(Canvas canvas, Size size) {
    Offset at(int i) =>
        Offset(_nodes[i].dx * size.width, _nodes[i].dy * size.height);
    final line = Paint()
      ..color = EvColors.indigo.withValues(alpha: 0.35)
      ..strokeWidth = 1.5;
    for (final (a, b) in _edges) {
      canvas.drawLine(at(a), at(b), line);
    }
    for (var i = 0; i < _nodes.length; i++) {
      final center = i == 0;
      canvas.drawCircle(
        at(i),
        center ? 14 : 8,
        Paint()
          ..color = (center ? EvColors.teal : EvColors.indigo).withValues(
            alpha: center ? 0.9 : 0.7,
          ),
      );
    }
  }

  @override
  bool shouldRepaint(_GraphPainter old) => false;
}
