package lk.sliit.j26se350.echo_vault

import org.w3c.dom.Document
import org.w3c.dom.Element
import java.io.File
import java.io.IOException
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult

/**
 * The LAN-only settings the app enforces on the embedded Syncthing (A5, FR5/NFR4). Option
 * names are those of Syncthing's config (https://docs.syncthing.net/users/config.html, docs
 * tag v2.1.0, for the pinned v2.1.6); config.xml and the REST JSON use the same names, except
 * that the repeated XML element `listenAddress` is the JSON array `listenAddresses`.
 */
internal object LanOnly {
    /** TCP only: `default` would add QUIC (which uses STUN) and the relay pool. */
    const val LISTEN_ADDRESS = "tcp://0.0.0.0:22000"

    val OPTIONS: Map<String, Any> = linkedMapOf(
        "globalAnnounceEnabled" to false, // global discovery off
        "localAnnounceEnabled" to true, // local (LAN broadcast) discovery on
        "relaysEnabled" to false, // relays off
        "natEnabled" to false, // UPnP / NAT-PMP port mapping (NAT traversal) off
        "stunKeepaliveStartS" to 0, // 0 = never contact STUN servers
        "autoUpgradeIntervalH" to 0, // 0 = automatic upgrades off
        "urAccepted" to -1, // -1 = usage reporting declined
        "crashReportingEnabled" to false, // crash reporting off
        "startBrowser" to false,
    )
}

/**
 * Edits the embedded Syncthing's config.xml while Syncthing is not running, so that even the
 * first start (right after `syncthing generate`, whose defaults enable global discovery,
 * relays, NAT, upgrades and crash reporting) is LAN-only before any network activity. The
 * same settings are then enforced and verified through the REST API on every start.
 */
internal object SyncthingConfigFile {
    /** The GUI/REST address and API key currently in [file], or null if absent. */
    fun guiEndpoint(file: File): Pair<String, String>? {
        if (!file.exists()) return null
        val gui = parse(file).documentElement.child("gui") ?: return null
        val address = gui.child("address")?.textContent?.trim().orEmpty()
        val apiKey = gui.child("apikey")?.textContent?.trim().orEmpty()
        return if (address.isEmpty() || apiKey.isEmpty()) null else address to apiKey
    }

    /** Applies [LanOnly] and binds the GUI/REST to [guiAddress] with [apiKey], without TLS. */
    fun applyLanOnly(file: File, guiAddress: String, apiKey: String) {
        val doc = parse(file)
        val root = doc.documentElement
        val gui = root.child("gui") ?: throw IOException("config.xml has no <gui> element")
        gui.setAttribute("enabled", "true")
        gui.setAttribute("tls", "false")
        gui.setText("address", guiAddress)
        gui.setText("apikey", apiKey)

        val options = root.child("options") ?: throw IOException("config.xml has no <options>")
        options.children("listenAddress").forEach { options.removeChild(it) }
        options.appendChild(doc.createElement("listenAddress").apply {
            textContent = LanOnly.LISTEN_ADDRESS
        })
        for ((name, value) in LanOnly.OPTIONS) options.setText(name, value.toString())

        // Write next to the original, then replace it in one rename.
        val tmp = File(file.parentFile, "${file.name}.echo_vault.tmp")
        TransformerFactory.newInstance().newTransformer()
            .transform(DOMSource(doc), StreamResult(tmp))
        if (!tmp.renameTo(file)) throw IOException("Could not replace ${file.path}")
    }

    private fun parse(file: File): Document =
        DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file)

    private fun Element.children(name: String): List<Element> {
        val nodes = childNodes
        return (0 until nodes.length).mapNotNull { nodes.item(it) as? Element }
            .filter { it.tagName == name }
    }

    private fun Element.child(name: String): Element? = children(name).firstOrNull()

    private fun Element.setText(name: String, value: String) {
        val element = child(name)
            ?: ownerDocument.createElement(name).also { appendChild(it) }
        element.textContent = value
    }
}
