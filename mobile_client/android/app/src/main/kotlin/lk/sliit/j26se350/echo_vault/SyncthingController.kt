package lk.sliit.j26se350.echo_vault

import android.content.Context
import android.content.pm.ApplicationInfo
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.security.SecureRandom
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * Runs the embedded Syncthing (A5): the official, unmodified v2.1.6 linux-arm64 executable,
 * installed as `libsyncthing.so` in nativeLibraryDir, with its home (config, keys, database)
 * in app-private `files/syncthing/`. It shares `files/outbox/` as one send-only folder with
 * one PC at a fixed LAN address.
 *
 * LAN-only (FR5/NFR4): before every start, config.xml gets the [LanOnly] settings and a fresh
 * GUI/REST endpoint (127.0.0.1, random free port, random API key); after the start the same
 * settings are applied and read back through the REST API ([status] reports the result).
 *
 * All methods block (process start, HTTP to 127.0.0.1): call them on [executor], never on
 * the main thread. One instance per app process ([shared]).
 */
internal class SyncthingController(context: Context) {
    private val appContext = context.applicationContext
    private val binary = File(appContext.applicationInfo.nativeLibraryDir, "libsyncthing.so")
    private val home = File(appContext.filesDir, "syncthing")
    private val config = File(home, "config.xml")
    private val outbox = File(appContext.filesDir, "outbox")
    private val logOutput =
        (appContext.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
    private val random = SecureRandom()
    private val logTail = ArrayDeque<String>()

    @Volatile private var process: Process? = null
    private var rest: SyncthingRest? = null
    private var guiAddress: String? = null
    private var myId: String? = null
    private var lastError: String? = null
    @Volatile private var exitCode: Int? = null

    /** `libsyncthing.so --version`, e.g. `syncthing v2.1.6 "Hafnium Hornet" (go1.27.1 linux-arm64) …`. */
    @Synchronized
    fun version(): String {
        val p = ProcessBuilder(binary.path, "--version").redirectErrorStream(true)
            .also { environment(it) }.start()
        p.outputStream.close()
        val out = p.inputStream.bufferedReader().readText().trim()
        if (!p.waitFor(30, TimeUnit.SECONDS)) {
            p.destroyForcibly()
            throw IOException("--version timed out")
        }
        if (p.exitValue() != 0) throw IOException("--version exited ${p.exitValue()}: $out")
        return out
    }

    /** Starts Syncthing if it is not running; idempotent. Returns [status]. */
    @Synchronized
    fun start(): Map<String, Any?> {
        if (process?.isAlive == true && rest != null) return status()
        lastError = null
        try {
            if (!binary.canExecute()) throw IOException("${binary.path} is missing or not executable")
            note(version())
            home.mkdirs()
            outbox.mkdirs()
            File(outbox, MARKER).mkdirs()
            if (!config.exists()) generate()
            stopStaleInstance()
            val address = "127.0.0.1:${freeLoopbackPort()}"
            val apiKey = randomToken(32)
            SyncthingConfigFile.applyLanOnly(config, address, apiKey)
            val client = SyncthingRest(address, apiKey)
            launchAndWait(client)
            enforce(client, address, apiKey)
            if (client.getObject("/rest/config/restart-required").optBoolean("requiresRestart")) {
                note("config change requires a restart; restarting once")
                stopProcess()
                launchAndWait(client)
                enforce(client, address, apiKey)
            }
            note("running: REST on $address, folder $FOLDER_ID -> ${outbox.path}")
        } catch (e: Exception) {
            lastError = e.message ?: e.toString()
            note("start failed: $lastError")
            stopProcess()
        }
        return status()
    }

    /** Asks Syncthing to shut down; kills it if it has not exited within a few seconds. */
    @Synchronized
    fun stop() {
        stopProcess()
        note("stopped")
    }

    /**
     * Sets the one PC this phone sends to: its device ID and fixed address (`tcp://IP:port`,
     * private IPv4 only), and shares the outbox folder with it (removing any previous PC).
     */
    @Synchronized
    fun setPeer(deviceId: String, address: String): Map<String, Any?> {
        val client = rest ?: throw IOException("Syncthing is not running")
        val me = myId ?: throw IOException("Own device ID unknown")
        require(isLanAddress(address)) { "Address must be tcp://<private IPv4>:<port>" }
        val checked = client.getObject("/rest/svc/deviceid" + SyncthingRest.query("id" to deviceId))
        checked.optString("error").takeIf { it.isNotEmpty() }?.let {
            throw IllegalArgumentException("Invalid device ID: $it")
        }
        val id = checked.getString("id")
        require(id != me) { "That is this phone's own device ID" }

        val device = client.getArray("/rest/config/devices").objects()
            .firstOrNull { it.optString("deviceID") == id }
            ?: client.getObject("/rest/config/defaults/device")
        device.put("deviceID", id)
        device.put("name", PC_NAME)
        device.put("addresses", JSONArray(listOf(address)))
        device.put("introducer", false)
        device.put("autoAcceptFolders", false)
        device.put("paused", false)
        client.post("/rest/config/devices", device)

        val folder = client.getObject("/rest/config/folders/$FOLDER_ID")
        folder.put("devices", JSONArray(listOf(folderDevice(me), folderDevice(id))))
        client.post("/rest/config/folders", folder)

        for (old in client.getArray("/rest/config/devices").objects()) {
            val oldId = old.optString("deviceID")
            if (oldId != me && oldId != id) client.delete("/rest/config/devices/$oldId")
        }
        note("peer set: ${id.take(7)}… at $address")
        return status()
    }

    /** Requests an immediate scan of [sub] (relative to the outbox) so new files go out now. */
    @Synchronized
    fun scan(sub: String?): Boolean {
        val client = rest ?: return false
        if (process?.isAlive != true) return false
        val params = mutableListOf("folder" to FOLDER_ID)
        if (!sub.isNullOrEmpty()) params += "sub" to sub
        client.post("/rest/db/scan" + SyncthingRest.query(*params.toTypedArray()))
        return true
    }

    /** PNG QR code of this device's ID, rendered by Syncthing's GUI (`/qr/`). */
    @Synchronized
    fun qrPng(): ByteArray {
        val client = rest ?: throw IOException("Syncthing is not running")
        val id = myId ?: throw IOException("Own device ID unknown")
        return client.getBytes("/qr/" + SyncthingRest.query("text" to id))
    }

    /** Running state, LAN-only check, this device's ID, the PC's connection and pending chunks. */
    @Synchronized
    fun status(): Map<String, Any?> {
        val running = process?.isAlive == true
        val map = linkedMapOf<String, Any?>(
            "running" to running,
            "error" to lastError,
            "exitCode" to exitCode,
            "folderId" to FOLDER_ID,
            "folderPath" to outbox.path,
        )
        val client = rest
        if (!running || client == null) return map
        try {
            map["version"] = client.getObject("/rest/system/version").optString("version")
            map["deviceId"] = myId
            map["guiAddress"] = guiAddress
            val options = client.getObject("/rest/config/options")
            val lanOnly = linkedMapOf<String, Any?>()
            for (name in LanOnly.OPTIONS.keys) lanOnly[name] = options.opt(name)
            lanOnly["listenAddresses"] = options.optJSONArray("listenAddresses")?.strings()
            map["lanOnly"] = lanOnly
            map["lanOnlyVerified"] = lanOnlyHolds(options) &&
                client.getObject("/rest/config/gui").optString("address") == guiAddress
            val system = client.getObject("/rest/system/status")
            map["listeners"] = system.optJSONObject("connectionServiceStatus")?.keyList()
            // Discovery mechanisms that work, and those that failed (name: error).
            val discovery = system.optJSONObject("discoveryStatus") ?: JSONObject()
            val failed = discovery.keyList().filter {
                !discovery.getJSONObject(it).isNull("error")
            }
            map["discovery"] = discovery.keyList() - failed.toSet()
            map["discoveryErrors"] = failed.map {
                "$it: ${discovery.getJSONObject(it).optString("error")}"
            }

            val folder = client.getObject("/rest/config/folders/$FOLDER_ID")
            map["folderType"] = folder.optString("type")
            map["folderState"] = client.getObject(
                "/rest/db/status" + SyncthingRest.query("folder" to FOLDER_ID),
            ).optString("state")

            val connections = client.getObject("/rest/system/connections")
                .optJSONObject("connections") ?: JSONObject()
            map["connections"] = connections.keyList().mapNotNull { id ->
                val c = connections.getJSONObject(id)
                if (!c.optBoolean("connected")) return@mapNotNull null
                mapOf("deviceId" to id, "address" to c.optString("address"), "type" to c.optString("type"))
            }

            val pc = client.getArray("/rest/config/devices").objects()
                .firstOrNull { it.optString("deviceID") != myId }
            if (pc != null) {
                val pcId = pc.getString("deviceID")
                map["pcDeviceId"] = pcId
                map["pcAddress"] = pc.optJSONArray("addresses")?.strings()?.firstOrNull()
                val c = connections.optJSONObject(pcId)
                map["pcConnected"] = c?.optBoolean("connected") ?: false
                map["pcConnectionAddress"] = c?.optString("address")?.ifEmpty { null }
                map["pcConnectionType"] = c?.optString("type")?.ifEmpty { null }
                val completion = client.getObject(
                    "/rest/db/completion" +
                        SyncthingRest.query("folder" to FOLDER_ID, "device" to pcId),
                )
                val needItems = completion.optInt("needItems")
                map["remoteState"] = completion.optString("remoteState").ifEmpty { null }
                map["pendingItems"] = needItems
                map["pendingChunks"] = if (needItems == 0) 0 else pendingChunks(client, pcId)
            }
        } catch (e: Exception) {
            map["error"] = "status: ${e.message ?: e}"
        }
        return map
    }

    /** Recent Syncthing output and controller notes (newest last). */
    @Synchronized
    fun recentLog(): List<String> = synchronized(logTail) { logTail.toList() }

    // --- internals -------------------------------------------------------------------------

    private fun generate() {
        note("first run: generating keys and config")
        val p = ProcessBuilder(
            binary.path, "generate", "--home=${home.path}", "--no-port-probing",
            "--gui-user=$GUI_USER", "--gui-password=-",
        ).redirectErrorStream(true).also { environment(it) }.start()
        // A random GUI password nobody knows: the web GUI stays locked even to other apps on
        // this phone; the app uses the REST API with the API key instead.
        p.outputStream.use { it.write(randomToken(32).toByteArray()) }
        val out = p.inputStream.bufferedReader().readText()
        out.lineSequence().filter { it.isNotBlank() }.forEach { output(it) }
        if (!p.waitFor(60, TimeUnit.SECONDS)) {
            p.destroyForcibly()
            throw IOException("generate timed out")
        }
        if (p.exitValue() != 0 || !config.exists()) {
            throw IOException("generate exited ${p.exitValue()}")
        }
    }

    /** Shuts down an instance left over from an earlier app process, if one still answers. */
    private fun stopStaleInstance() {
        val (address, apiKey) = SyncthingConfigFile.guiEndpoint(config) ?: return
        val old = SyncthingRest(address, apiKey)
        if (!old.healthy(300)) return
        note("an earlier instance answers on $address; shutting it down")
        try {
            old.post("/rest/system/shutdown")
        } catch (e: IOException) {
            note("shutdown request failed: ${e.message}")
        }
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10)
        while (old.healthy(300) && System.nanoTime() < deadline) Thread.sleep(200)
    }

    private fun launchAndWait(client: SyncthingRest) {
        exitCode = null
        val p = ProcessBuilder(
            binary.path, "serve", "--home=${home.path}",
            "--no-browser", "--no-restart", "--no-upgrade",
        ).redirectErrorStream(true).also { environment(it) }.start()
        p.outputStream.close()
        process = p
        thread(name = "syncthing-output", isDaemon = true) {
            try {
                p.inputStream.bufferedReader().forEachLine { output(it) }
            } catch (_: IOException) {
                // Stream closed when the process ends.
            }
            val code = p.waitFor()
            if (process === p) exitCode = code
            note("process exited with code $code")
        }
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(STARTUP_TIMEOUT_S)
        while (true) {
            if (!p.isAlive) throw IOException("Syncthing exited during startup (code ${p.exitValue()})")
            val error = client.healthError(300) ?: break
            if (System.nanoTime() > deadline) {
                throw IOException("REST API did not answer within ${STARTUP_TIMEOUT_S}s: $error")
            }
            Thread.sleep(100)
        }
        rest = client
    }

    /** Applies and verifies the LAN-only settings, device name and outbox folder over REST. */
    private fun enforce(client: SyncthingRest, address: String, apiKey: String) {
        val options = client.getObject("/rest/config/options")
        for ((name, value) in LanOnly.OPTIONS) options.put(name, value)
        options.put("listenAddresses", JSONArray(listOf(LanOnly.LISTEN_ADDRESS)))
        client.put("/rest/config/options", options)

        val gui = client.getObject("/rest/config/gui")
        if (gui.optString("address") != address || gui.optString("apiKey") != apiKey ||
            gui.optBoolean("useTLS", false)
        ) {
            throw IOException("GUI is not on $address with the app's API key")
        }
        guiAddress = address

        val me = client.getObject("/rest/system/status").getString("myID")
        myId = me
        val self = client.getObject("/rest/config/devices/$me")
        if (self.optString("name") != DEVICE_NAME) {
            self.put("name", DEVICE_NAME) // generate uses the host name
            client.put("/rest/config/devices/$me", self)
        }

        ensureFolder(client, me)

        val check = client.getObject("/rest/config/options")
        if (!lanOnlyHolds(check)) throw IOException("LAN-only options did not apply: $check")
    }

    private fun ensureFolder(client: SyncthingRest, me: String) {
        val existing = try {
            client.getObject("/rest/config/folders/$FOLDER_ID")
        } catch (e: SyncthingRest.HttpError) {
            if (e.code != 404) throw e
            null
        }
        val folder = existing ?: client.getObject("/rest/config/defaults/folder").apply {
            put("devices", JSONArray(listOf(folderDevice(me))))
        }
        folder.put("id", FOLDER_ID)
        folder.put("label", FOLDER_LABEL)
        folder.put("path", outbox.path)
        folder.put("type", "sendonly")
        folder.put("fsWatcherEnabled", true)
        folder.put("fsWatcherDelayS", 1) // backup only: the app requests a scan per new file
        folder.put("ignorePerms", true)
        folder.put("paused", false)
        client.post("/rest/config/folders", folder)
        // staging/ is a sibling of outbox/, so it is never inside the folder; the pattern
        // only guards against a future layout change.
        client.post(
            "/rest/db/ignores" + SyncthingRest.query("folder" to FOLDER_ID),
            JSONObject().put("ignore", JSONArray(listOf("/staging"))),
        )
    }

    private fun lanOnlyHolds(options: JSONObject): Boolean =
        LanOnly.OPTIONS.all { (name, value) -> options.opt(name)?.toString() == value.toString() } &&
            options.optJSONArray("listenAddresses")?.strings() == listOf(LanOnly.LISTEN_ADDRESS)

    private fun pendingChunks(client: SyncthingRest, pcId: String): Int {
        var count = 0
        var page = 1
        while (true) {
            val files = client.getObject(
                "/rest/db/remoteneed" + SyncthingRest.query(
                    "folder" to FOLDER_ID, "device" to pcId,
                    "page" to "$page", "perpage" to "$REMOTE_NEED_PAGE",
                ),
            ).optJSONArray("files") ?: break
            count += files.objects().count { it.optString("name").endsWith(".opus") }
            if (files.length() < REMOTE_NEED_PAGE) break
            page++
        }
        return count
    }

    private fun stopProcess() {
        val p = process ?: return
        val client = rest
        rest = null
        if (p.isAlive && client != null) {
            try {
                client.post("/rest/system/shutdown")
            } catch (e: IOException) {
                note("shutdown request failed: ${e.message}")
            }
        }
        if (!p.waitFor(5, TimeUnit.SECONDS)) {
            p.destroy()
            if (!p.waitFor(2, TimeUnit.SECONDS)) p.destroyForcibly()
        }
        process = null
    }

    private fun environment(builder: ProcessBuilder) {
        val env = builder.environment()
        env["HOME"] = home.path
        env["TMPDIR"] = appContext.cacheDir.path
        // No overrides from the inherited environment.
        env.keys.filter { it.startsWith("ST") }.forEach { env.remove(it) }
    }

    private fun freeLoopbackPort(): Int =
        ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { it.localPort }

    private fun randomToken(length: Int): String =
        String(CharArray(length) { TOKEN_CHARS[random.nextInt(TOKEN_CHARS.length)] })

    private fun output(line: String) {
        remember(line)
        if (logOutput) Log.i(TAG, line)
    }

    private fun note(message: String) {
        remember("[controller] $message")
        if (logOutput) Log.i(TAG, "[controller] $message")
    }

    private fun remember(line: String) = synchronized(logTail) {
        logTail.addLast(line)
        while (logTail.size > LOG_TAIL_LINES) logTail.removeFirst()
    }

    companion object {
        /** The one thread all controller calls run on, in submission order. */
        val executor: ExecutorService = Executors.newSingleThreadExecutor { r ->
            Thread(r, "syncthing-control").apply { isDaemon = true }
        }

        @Volatile private var instance: SyncthingController? = null

        fun shared(context: Context): SyncthingController =
            instance ?: synchronized(this) {
                instance ?: SyncthingController(context).also { instance = it }
            }

        const val TAG = "Syncthing"
        const val FOLDER_ID = "echo-vault-outbox"
        const val FOLDER_LABEL = "Echo Vault outbox"
        const val DEVICE_NAME = "Echo Vault"
        const val PC_NAME = "PC"
        const val GUI_USER = "echo-vault"
        const val MARKER = ".stfolder"
        const val STARTUP_TIMEOUT_S = 60L
        const val REMOTE_NEED_PAGE = 500
        const val LOG_TAIL_LINES = 300
        const val TOKEN_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

        private val TCP_IPV4 = Regex("""^tcp://(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3}):(\d{1,5})$""")

        /** `tcp://a.b.c.d:port` with a private (RFC 1918) or link-local IPv4 address. */
        fun isLanAddress(address: String): Boolean {
            val m = TCP_IPV4.matchEntire(address) ?: return false
            val (a, b, c, d) = m.groupValues.drop(1).take(4).map { it.toInt() }
            val port = m.groupValues[5].toInt()
            if (listOf(a, b, c, d).any { it > 255 } || port !in 1..65535) return false
            return a == 10 || (a == 172 && b in 16..31) || (a == 192 && b == 168) ||
                (a == 169 && b == 254)
        }

        private fun folderDevice(id: String) =
            JSONObject().put("deviceID", id).put("introducedBy", "").put("encryptionPassword", "")

        private fun JSONArray.objects(): List<JSONObject> = (0 until length()).map { getJSONObject(it) }

        private fun JSONArray.strings(): List<String> = (0 until length()).map { getString(it) }

        private fun JSONObject.keyList(): List<String> = keys().asSequence().toList()
    }
}
