plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "lk.sliit.j26se350.echo_vault"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "lk.sliit.j26se350.echo_vault"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        // API 29 (Android 10): MediaMuxer OGG output and the platform Opus encoder
        // (c2.android.opus.encoder) used for chunk encoding (A4, approved).
        minSdk = 29
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    packaging {
        jniLibs {
            // A5 (approved): jniLibs/arm64-v8a/libsyncthing.so is the Syncthing executable
            // (fetched by tool/fetch_syncthing.ps1), not a library. Legacy packaging stores it
            // so the installer extracts it into nativeLibraryDir (extractNativeLibs=true): the
            // only app location Android 10+ allows executing files from.
            useLegacyPackaging = true
            // Package the verified binary unchanged (never stripped).
            keepDebugSymbols += "**/libsyncthing.so"
        }
    }

    buildTypes {
        release {
            // TODO: Add your own signing config for the release build.
            // Signing with the debug keys for now, so `flutter run --release` works.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
