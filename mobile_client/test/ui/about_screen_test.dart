import 'dart:io';

import 'package:echo_vault/ui/about_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets(
    'shows the app version, Syncthing, its source links and licence',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: AboutScreen(
            appVersion: Future.value('1.0.0+1'),
            licenseText: () async => 'Mozilla Public License Version 2.0\n…',
          ),
        ),
      );
      await tester.pump();
      expect(find.text('Version 1.0.0+1'), findsOneWidget);
      expect(find.textContaining('Syncthing v2.1.6'), findsOneWidget);
      expect(find.textContaining('Mozilla Public License 2.0'), findsWidgets);
      expect(
        find.text('https://github.com/syncthing/syncthing'),
        findsOneWidget,
      );
      expect(
        find.text('https://github.com/syncthing/syncthing/releases/tag/v2.1.6'),
        findsOneWidget,
      );
      final license = tester.widget<SelectableText>(
        find.byKey(AboutScreen.licenseKey),
      );
      expect(license.data, startsWith('Mozilla Public License Version 2.0'));
    },
  );

  testWidgets('the bundled asset is the release’s MPL-2.0 text', (
    tester,
  ) async {
    final text = await tester.runAsync(loadSyncthingLicense);
    expect(text, startsWith('Mozilla Public License Version 2.0'));
    expect(text, contains('Exhibit A - Source Code Form License Notice'));
    // Same bytes as the file in the repository (copied from the release
    // tarball by tool/fetch_syncthing.ps1).
    expect(text, File(kSyncthingLicenseAsset).readAsStringSync());
  });

  test('the pinned version matches tool/fetch_syncthing.ps1', () {
    final script = File('tool/fetch_syncthing.ps1').readAsStringSync();
    expect(script, contains("\$Version = '$kSyncthingVersion'"));
  });
}
