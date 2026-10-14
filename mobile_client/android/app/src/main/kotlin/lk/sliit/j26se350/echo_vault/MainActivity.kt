package lk.sliit.j26se350.echo_vault

import android.Manifest
import android.content.pm.PackageManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Hosts the Flutter UI and answers microphone permission requests from Dart over a
 * MethodChannel, using only platform APIs (no third-party permission plugin).
 *
 * Channel: `lk.sliit.j26se350.echo_vault/permissions`
 * Method:  `requestMicrophone` -> "granted" | "denied" | "permanentlyDenied"
 */
class MainActivity : FlutterActivity() {
    private var pendingResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "requestMicrophone" -> requestMicrophone(result)
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

    private companion object {
        const val CHANNEL = "lk.sliit.j26se350.echo_vault/permissions"
        const val REQUEST_CODE = 4101
        const val GRANTED = "granted"
        const val DENIED = "denied"
        const val PERMANENTLY_DENIED = "permanentlyDenied"
    }
}
