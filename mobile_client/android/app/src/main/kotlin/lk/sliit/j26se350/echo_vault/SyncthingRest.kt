package lk.sliit.j26se350.echo_vault

import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Minimal client for the embedded Syncthing's REST API on 127.0.0.1 (A5). Every request
 * carries the API key; nothing else is ever contacted. Blocking: call off the main thread.
 *
 * Config changes use GET, then PUT or POST of the whole object (see
 * https://docs.syncthing.net/rest/config.html), so no PATCH support is needed.
 */
internal class SyncthingRest(private val address: String, private val apiKey: String) {
    class HttpError(val code: Int, message: String) : IOException("HTTP $code: $message")

    fun getObject(path: String): JSONObject = JSONObject(text("GET", path))

    fun getArray(path: String): JSONArray = JSONArray(text("GET", path))

    fun getBytes(path: String): ByteArray = request("GET", path, null)

    fun put(path: String, body: Any) {
        request("PUT", path, body.toString())
    }

    fun post(path: String, body: Any? = null): String = text("POST", path, body?.toString())

    fun delete(path: String) {
        request("DELETE", path, null)
    }

    /** True if `/rest/noauth/health` answers `{"status": "OK"}` within [timeoutMs]. */
    fun healthy(timeoutMs: Int = 500): Boolean = healthError(timeoutMs) == null

    /** Null if `/rest/noauth/health` answers `{"status": "OK"}`, else why not. */
    fun healthError(timeoutMs: Int = 500): String? = try {
        val status = JSONObject(text("GET", "/rest/noauth/health", null, timeoutMs)).optString("status")
        if (status == "OK") null else "health status \"$status\""
    } catch (e: IOException) {
        e.toString()
    } catch (e: org.json.JSONException) {
        e.toString()
    }

    private fun text(method: String, path: String, body: String? = null, timeoutMs: Int? = null) =
        String(request(method, path, body, timeoutMs), Charsets.UTF_8)

    private fun request(
        method: String,
        path: String,
        body: String?,
        timeoutMs: Int? = null,
    ): ByteArray {
        val connection = URL("http://$address$path").openConnection() as HttpURLConnection
        try {
            connection.requestMethod = method
            connection.connectTimeout = timeoutMs ?: CONNECT_TIMEOUT_MS
            connection.readTimeout = timeoutMs ?: READ_TIMEOUT_MS
            connection.useCaches = false
            connection.setRequestProperty("X-API-Key", apiKey)
            if (body != null) {
                val bytes = body.toByteArray(Charsets.UTF_8)
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json")
                connection.setFixedLengthStreamingMode(bytes.size)
                connection.outputStream.use { it.write(bytes) }
            }
            val code = connection.responseCode
            if (code !in 200..299) {
                val message = connection.errorStream?.use { String(it.readBytes(), Charsets.UTF_8) }
                throw HttpError(code, message?.trim().orEmpty().take(300))
            }
            return connection.inputStream.use { it.readBytes() }
        } finally {
            connection.disconnect()
        }
    }

    companion object {
        const val CONNECT_TIMEOUT_MS = 2_000
        const val READ_TIMEOUT_MS = 15_000

        fun query(vararg pairs: Pair<String, String>): String =
            pairs.joinToString("&", prefix = "?") { (k, v) ->
                "$k=${URLEncoder.encode(v, "UTF-8")}"
            }
    }
}
