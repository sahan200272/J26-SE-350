package lk.sliit.j26se350.echo_vault

import android.Manifest
import android.content.pm.PackageManager
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat
import android.os.Build
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Hosts the Flutter UI and answers platform requests from Dart over one MethodChannel,
 * using only platform APIs (no third-party plugin).
 *
 * Channel: `lk.sliit.j26se350.echo_vault/permissions`
 * - `requestMicrophone` -> "granted" | "denied" | "permanentlyDenied"
 * - `setKeepScreenOn(Boolean)` -> null; sets or clears FLAG_KEEP_SCREEN_ON on this window
 * - `getFilesDir` -> absolute path of the app-private files directory
 * - `listOpusEncoders` -> list of maps describing audio/opus encoders (informational)
 */
class MainActivity : FlutterActivity() {
    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "requestMicrophone" -> requestMicrophone(result)
                    "setKeepScreenOn" -> setKeepScreenOn(call.arguments as? Boolean, result)
                    "getFilesDir" -> result.success(filesDir.absolutePath)
                    "listOpusEncoders" -> result.success(listOpusEncoders())
                    else -> result.notImplemented()
                }
            }
    }

    private fun requestMicrophone(result: MethodChannel.Result) {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            result.success(GRANTED)
            return
        }
        if (pendingResult != null) {
            result.error("IN_PROGRESS", "A microphone permission request is already running.", null)
            return
        }
        pendingResult = result
        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQUEST_CODE)
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_CODE) return
        val result = pendingResult ?: return
        pendingResult = null
        val status = when {
            // Empty results mean the dialog was dismissed without a decision.
            grantResults.isEmpty() -> DENIED
            grantResults[0] == PackageManager.PERMISSION_GRANTED -> GRANTED
            // After a denial, no rationale means the system will not show the dialog again.
            shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO) -> DENIED
            else -> PERMANENTLY_DENIED
        }
        result.success(status)
    }

    /** Window flag only: no WAKE_LOCK permission needed, and it ends with the activity. */
    private fun setKeepScreenOn(on: Boolean?, result: MethodChannel.Result) {
        if (on == null) {
            result.error("BAD_ARGS", "setKeepScreenOn expects a bool.", null)
            return
        }
        if (on) {
            window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
        result.success(null)
    }

    /** Encoders in MediaCodecList(REGULAR_CODECS) that accept audio/opus. Not used for encoding. */
    private fun listOpusEncoders(): List<Map<String, Any?>> =
        MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos
            .filter { it.isEncoder }
            .mapNotNull { info ->
                val type = info.supportedTypes
                    .firstOrNull { it.equals(MediaFormat.MIMETYPE_AUDIO_OPUS, ignoreCase = true) }
                    ?: return@mapNotNull null
                describeAudioEncoder(info, type)
            }

    private fun describeAudioEncoder(info: MediaCodecInfo, type: String): Map<String, Any?> {
        val audio = info.getCapabilitiesForType(type).audioCapabilities
        val map = mutableMapOf<String, Any?>(
            "name" to info.name,
            "type" to type,
            // Null means any rate within sampleRateRanges.
            "sampleRates" to audio?.supportedSampleRates?.toList(),
            "sampleRateRanges" to audio?.supportedSampleRateRanges?.map { listOf(it.lower, it.upper) },
            "maxInputChannelCount" to audio?.maxInputChannelCount,
            "bitrateRange" to audio?.bitrateRange?.let { listOf(it.lower, it.upper) },
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            map["canonicalName"] = info.canonicalName
            map["isAlias"] = info.isAlias
            map["hardwareAccelerated"] = info.isHardwareAccelerated
            map["softwareOnly"] = info.isSoftwareOnly
            map["vendor"] = info.isVendor
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            map["minInputChannelCount"] = audio?.minInputChannelCount
        }
        return map
    }

    private companion object {
        const val CHANNEL = "lk.sliit.j26se350.echo_vault/permissions"
        const val REQUEST_CODE = 4101
        const val GRANTED = "granted"
        const val DENIED = "denied"
        const val PERMANENTLY_DENIED = "permanentlyDenied"
    }
}
