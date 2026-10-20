import 'dart:io';

/// Remembers whether the welcome screens have been seen.
abstract interface class OnboardingStore {
  Future<bool> isComplete();
  Future<void> markComplete();
}

/// Stores the flag as an empty marker file in the app-private `files/`
/// directory (no extra dependency; excluded from Android backup like the
/// rest of the app's data).
class FileOnboardingStore implements OnboardingStore {
  FileOnboardingStore(this._filesDir);

  final Future<String> _filesDir;

  Future<File> _file() async =>
      File('${await _filesDir}/prefs/onboarding_complete');

  @override
  Future<bool> isComplete() async {
    try {
      return await (await _file()).exists();
    } catch (_) {
      // If storage cannot be read, show the welcome screens again.
      return false;
    }
  }

  @override
  Future<void> markComplete() async {
    try {
      final file = await _file();
      await file.parent.create(recursive: true);
      await file.writeAsString('1', flush: true);
    } catch (_) {
      // Not critical: the welcome screens show again next launch.
    }
  }
}

/// A one-time flag (e.g. "the microphone explainer was shown") stored like
/// [FileOnboardingStore], as a marker file `files/prefs/<name>`.
class FileFlagStore implements OnboardingStore {
  FileFlagStore(this._filesDir, this.name);

  final Future<String> _filesDir;
  final String name;

  Future<File> _file() async => File('${await _filesDir}/prefs/$name');

  @override
  Future<bool> isComplete() async {
    try {
      return await (await _file()).exists();
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> markComplete() async {
    try {
      final file = await _file();
      await file.parent.create(recursive: true);
      await file.writeAsString('1', flush: true);
    } catch (_) {
      // Not critical: the flag is simply not remembered.
    }
  }
}

/// In-memory store (tests).
class MemoryOnboardingStore implements OnboardingStore {
  MemoryOnboardingStore({this.complete = false});

  bool complete;

  @override
  Future<bool> isComplete() async => complete;

  @override
  Future<void> markComplete() async => complete = true;
}
