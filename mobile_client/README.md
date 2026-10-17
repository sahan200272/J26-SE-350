## Echo Vault – Setup / Run

Android-only Flutter client for Component 1 (edge capture). See `CLAUDE.md` for scope and rules.

**Prerequisites:** Flutter stable (3.47.x, Dart 3.13), Android SDK with Android NDK
28.2.13676358 (Android Studio → SDK Manager → SDK Tools → NDK (Side by side)),
and a phone with USB or wireless debugging enabled.

```sh
cd mobile_client
flutter pub get
flutter analyze
flutter test
flutter build apk --debug      # build/app/outputs/flutter-apk/app-debug.apk
flutter run -d <device-id>     # see `flutter devices`
```

The app asks for microphone permission when **Start** is pressed. The main
`AndroidManifest.xml` declares only `RECORD_AUDIO` (no `INTERNET`).
