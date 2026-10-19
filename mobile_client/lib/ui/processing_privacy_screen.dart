import 'package:flutter/material.dart';

import '../capture/audio_capture.dart';
import '../encoding/opus_encoder.dart';
import 'components.dart';
import 'theme/app_theme.dart';

/// Where each step of Echo Vault runs, and which steps exist today.
enum StepStatus {
  phone('In this app', PillTone.positive, Icons.smartphone_rounded),
  pc('On your PC', PillTone.indigo, Icons.desktop_windows_outlined),
  planned('Planned', PillTone.neutral, Icons.schedule_rounded);

  const StepStatus(this.label, this.tone, this.icon);

  final String label;
  final PillTone tone;
  final IconData icon;
}

/// Processing & privacy: what happens to the user's voice in plain language,
/// what is implemented and what is planned, and (collapsed) the technical
/// details for researchers. Statements match the current implementation.
class ProcessingPrivacyScreen extends StatelessWidget {
  const ProcessingPrivacyScreen({super.key});

  static const technicalKey = Key('processing-technical');

  static const _steps = [
    (
      StepStatus.phone,
      Icons.touch_app_outlined,
      'You choose when to record',
      'Audio is captured only between Start and Stop. If you leave the app, '
          'recording pauses until you resume it.',
    ),
    (
      StepStatus.phone,
      Icons.hearing_rounded,
      'Your phone keeps only the speech',
      'Silent stretches are dropped on the phone, and speech is compressed '
          'into small audio files.',
    ),
    (
      StepStatus.phone,
      Icons.lan_outlined,
      'Sent to your own PC',
      'Recordings travel over your local network directly to the PC you '
          'paired. Nothing is uploaded to the cloud.',
    ),
    (
      StepStatus.pc,
      Icons.notes_rounded,
      'Your PC writes the transcript',
      'Echo Vault on your PC turns the speech into text on that computer.',
    ),
    (
      StepStatus.planned,
      Icons.record_voice_over_outlined,
      'Speakers and highlights',
      'Telling speakers apart and picking out names, places and dates.',
    ),
    (
      StepStatus.planned,
      Icons.hub_outlined,
      'Knowledge and assistant',
      'Connecting what you discussed and answering questions about it.',
    ),
    (
      StepStatus.planned,
      Icons.phone_android_rounded,
      'Results on this phone',
      'Seeing transcripts and notifications in this app.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Processing & privacy')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            EvSpace.xs,
            EvSpace.md,
            EvSpace.xl,
          ),
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: EvSpace.xxs),
              child: Text(
                'What happens to your voice, step by step, and what is '
                'still being built.',
                style: textTheme.bodyLarge?.copyWith(
                  color: EvColors.textMuted,
                ),
              ),
            ),
            const SectionTitle('How it works'),
            EvCard(
              child: Column(
                children: [
                  for (final (i, step) in _steps.indexed)
                    _StepRow(
                      number: i + 1,
                      status: step.$1,
                      icon: step.$2,
                      title: step.$3,
                      body: step.$4,
                      last: i == _steps.length - 1,
                    ),
                ],
              ),
            ),
            const SectionTitle('Our privacy commitments'),
            const GroupCard(
              children: [
                InfoRow(
                  icon: Icons.mic_off_outlined,
                  title: 'No background listening',
                  subtitle: 'No wake word. The microphone is used only while '
                      'you record.',
                ),
                InfoRow(
                  icon: Icons.cloud_off_outlined,
                  title: 'No cloud',
                  subtitle: 'Recordings go only to your own PC on your local '
                      'network.',
                ),
                InfoRow(
                  icon: Icons.backup_outlined,
                  title: 'No phone backup',
                  subtitle: 'Android cloud backup is turned off for Echo '
                      'Vault.',
                ),
                InfoRow(
                  icon: Icons.analytics_outlined,
                  title: 'No analytics or tracking',
                  subtitle: 'The app contains no analytics or telemetry.',
                ),
              ],
            ),
            const SizedBox(height: EvSpace.lg),
            const _TechnicalDetails(),
          ],
        ),
      ),
    );
  }
}

class _StepRow extends StatelessWidget {
  const _StepRow({
    required this.number,
    required this.status,
    required this.icon,
    required this.title,
    required this.body,
    required this.last,
  });

  final int number;
  final StepStatus status;
  final IconData icon;
  final String title;
  final String body;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final color = switch (status) {
      StepStatus.phone => EvColors.teal,
      StepStatus.pc => EvColors.indigo,
      StepStatus.planned => EvColors.textSubtle,
    };
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 36,
            child: Column(
              children: [
                IconBadge(icon, color: color, size: 36),
                if (!last)
                  Expanded(
                    child: Container(
                      width: 2,
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      color: EvColors.border,
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: EvSpace.sm),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: last ? 0 : EvSpace.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: textTheme.titleSmall),
                  const SizedBox(height: 2),
                  Text(body, style: textTheme.bodySmall),
                  const SizedBox(height: EvSpace.xs),
                  StatusPill(
                    label: status.label,
                    icon: status.icon,
                    tone: status.tone,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Collapsed by default: the implementation terms researchers need.
class _TechnicalDetails extends StatelessWidget {
  const _TechnicalDetails();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    Widget item(String title, String body) => Padding(
      padding: const EdgeInsets.only(bottom: EvSpace.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: textTheme.titleSmall),
          const SizedBox(height: 2),
          Text(body, style: textTheme.bodySmall),
        ],
      ),
    );
    return EvCard(
      key: ProcessingPrivacyScreen.technicalKey,
      padding: EdgeInsets.zero,
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(horizontal: EvSpace.md),
          childrenPadding: const EdgeInsets.fromLTRB(
            EvSpace.md,
            0,
            EvSpace.md,
            EvSpace.sm,
          ),
          leading: const Icon(Icons.code_rounded, color: EvColors.textMuted),
          title: Text('Technical details', style: textTheme.titleSmall),
          subtitle: Text(
            'For researchers and evaluators',
            style: textTheme.bodySmall,
          ),
          expandedCrossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            item(
              'Capture',
              '${kSampleRate ~/ 1000} kHz, '
                  '${kChannels == 1 ? 'mono' : '$kChannels channels'}, '
                  '16-bit PCM from the Android microphone, started and '
                  'stopped only by the user (FR1/FR2). Auto-pause when the '
                  'app leaves the foreground.',
            ),
            item(
              'Voice activity detection (VAD)',
              'Energy-based VAD baseline with onset/hangover segmentation, '
                  'running on the phone in pure Dart (FR3).',
            ),
            item(
              'Encoding and metadata',
              'Each speech segment is encoded as Ogg Opus at '
                  '${kDefaultOpusBitrate ~/ 1000} kbit/s with a JSON sidecar '
                  '(timestamps, VAD parameters, SHA-256). A session manifest '
                  'is written on Stop so the PC can detect missing chunks '
                  '(FR4, NFR7).',
            ),
            item(
              'Transfer',
              'An embedded Syncthing instance, configured LAN-only (no '
                  'global discovery, relays or NAT traversal; GUI/REST on '
                  '127.0.0.1), sends the outbox folder to the paired PC '
                  '(FR5/NFR4).',
            ),
            item(
              'On the PC',
              'Component 1 hub pipeline: Whisper-based transcription is '
                  'implemented; speaker diarization and named entity '
                  'recognition are planned. Agentic reasoning (C2), '
                  'notifications (C3) and the knowledge graph (C4) are '
                  'separate components and are not connected to this app.',
            ),
          ],
        ),
      ),
    );
  }
}
