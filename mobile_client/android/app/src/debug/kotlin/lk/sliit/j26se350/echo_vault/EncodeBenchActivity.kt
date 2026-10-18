package lk.sliit.j26se350.echo_vault

import android.app.Activity
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.MessageDigest
import kotlin.concurrent.thread

/**
 * Debug builds only (src/debug, not in release): times [OpusOggEncoder] on a 16-bit PCM WAV,
 * for the A5.1 encode-loop before/after measurement. Started from adb:
 *
 *     adb shell am start -n lk.sliit.j26se350.echo_vault/.EncodeBenchActivity \
 *         --es wav files/debug/segments/<name>.wav --ei runs 5 --es tag after
 *
 * `wav` is relative to the app's data directory. Runs one warm-up encode plus `runs` timed
 * encodes of the whole file (each with a new codec, as in the app), writing
 * `files/debug/bench/<tag>_<run>.opus`. Logs one `EncodeBench` line per run and a summary,
 * also written to `files/debug/bench/<tag>.json`. Stays on screen (keeping the screen on)
 * while it runs, so the process is never backgrounded mid-measurement, then finishes.
 */
class EncodeBenchActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val label = TextView(this).apply {
            text = "Encode benchmark running…"
            setPadding(48, 96, 48, 48)
        }
        setContentView(label)
        val wav = intent.getStringExtra("wav")
        val runs = intent.getIntExtra("runs", 5)
        val tag = intent.getStringExtra("tag") ?: "bench"
        val bitrate = intent.getIntExtra("bitrate", 32_000)
        thread(name = "encode-bench") {
            try {
                requireNotNull(wav) { "missing --es wav <path>" }
                bench(File(dataDir, wav), runs, tag, bitrate)
            } catch (e: Exception) {
                Log.e(TAG, "$tag failed", e)
            }
            runOnUiThread { finish() }
        }
    }

    private fun bench(wav: File, runs: Int, tag: String, bitrate: Int) {
        val (pcm, rate, channels) = readWav(wav)
        val audioMs = pcm.size / (2.0 * channels) / rate * 1000
        val outDir = File(filesDir, "debug/bench").apply { mkdirs() }
        val rows = JSONArray()
        val timed = mutableListOf<Double>()
        for (run in 0..runs) {
            val out = File(outDir, "${tag}_$run.opus")
            val start = System.nanoTime()
            val result = OpusOggEncoder.encode(pcm, rate, channels, bitrate, out)
            val ms = (System.nanoTime() - start) / 1e6
            val sha = sha256(out)
            if (run > 0) timed += ms
            Log.i(
                TAG,
                "$tag run $run${if (run == 0) " (warm-up)" else ""}: %.1f ms for %.0f ms of audio = %.2fx real time; %s; sha256 %s"
                    .format(ms, audioMs, audioMs / ms, result, sha),
            )
            rows.put(
                JSONObject().put("run", run).put("warmup", run == 0).put("encode_ms", ms)
                    .put("realtime_factor", audioMs / ms).put("packets", result.packets)
                    .put("output_bytes", result.outputBytes).put("sha256", sha)
                    .put("result", result.toString()),
            )
        }
        timed.sort()
        val median = if (timed.size % 2 == 1) timed[timed.size / 2]
        else (timed[timed.size / 2 - 1] + timed[timed.size / 2]) / 2
        val summary = JSONObject()
            .put("tag", tag).put("wav", wav.path).put("sample_rate", rate).put("channels", channels)
            .put("samples", pcm.size / (2 * channels)).put("audio_ms", audioMs).put("bitrate", bitrate)
            .put("timed_runs", timed.size).put("median_ms", median)
            .put("min_ms", timed.first()).put("max_ms", timed.last())
            .put("median_realtime_factor", audioMs / median)
            .put("median_encode_to_audio_ratio", median / audioMs)
            .put("runs", rows)
        File(outDir, "$tag.json").writeText(summary.toString(2))
        Log.i(
            TAG,
            "$tag summary: median %.1f ms (min %.1f, max %.1f) over %d runs for %.0f ms of audio = %.2fx real time (encode/audio %.3f)"
                .format(median, timed.first(), timed.last(), timed.size, audioMs, audioMs / median, median / audioMs),
        )
    }

    /** PCM bytes, sample rate and channel count of a 16-bit PCM WAV. */
    private fun readWav(file: File): Triple<ByteArray, Int, Int> {
        val bytes = file.readBytes()
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        require(String(bytes, 0, 4) == "RIFF" && String(bytes, 8, 4) == "WAVE") { "$file is not a WAV file" }
        var pos = 12
        var rate = 0
        var channels = 0
        while (pos + 8 <= bytes.size) {
            val id = String(bytes, pos, 4)
            val size = b.getInt(pos + 4)
            if (id == "fmt ") {
                require(b.getShort(pos + 8).toInt() == 1 && b.getShort(pos + 22).toInt() == 16) { "$file is not 16-bit PCM" }
                channels = b.getShort(pos + 10).toInt()
                rate = b.getInt(pos + 12)
            } else if (id == "data") {
                require(rate > 0) { "$file: data before fmt" }
                return Triple(bytes.copyOfRange(pos + 8, pos + 8 + size), rate, channels)
            }
            pos += 8 + size + (size and 1)
        }
        throw IllegalArgumentException("$file has no data chunk")
    }

    private fun sha256(file: File): String =
        MessageDigest.getInstance("SHA-256").digest(file.readBytes()).joinToString("") { "%02x".format(it) }

    private companion object {
        const val TAG = "EncodeBench"
    }
}
