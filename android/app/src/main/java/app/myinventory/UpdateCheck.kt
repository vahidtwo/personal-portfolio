package app.myinventory

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI

/** Pure logic for the «نسخهٔ تازه رسید» notice (unit tested; no Android APIs). */
object UpdateCheck {
    data class Info(
        val versionCode: Long,
        val versionName: String,
        val url: String,
        val notes: List<String>,
        /** Parsed but deliberately ignored: forced updates are not approved yet. */
        val minRequired: Long = 0,
    )

    /** Parses /api/app-version. Anything malformed or of the wrong type -> null. */
    fun parse(body: String?): Info? = runCatching {
        val obj = JSONObject(body ?: return null)
        val code = obj.opt("versionCode")
        val versionCode = when (code) {
            is Int -> code.toLong()
            is Long -> code
            else -> return null
        }
        if (versionCode <= 0) return null
        val name = obj.opt("versionName") as? String ?: return null
        val url = obj.opt("url") as? String ?: return null
        val notes = when (val raw = obj.opt("notes")) {
            null, JSONObject.NULL -> emptyList()
            is JSONArray -> (0 until raw.length()).mapNotNull { raw.opt(it) as? String }
            else -> return null
        }
        val minRequired = when (val raw = obj.opt("min_required")) {
            is Int -> raw.toLong()
            is Long -> raw
            else -> 0L // missing or wrong type: treat as no minimum
        }
        Info(versionCode, name, url, notes, minRequired)
    }.getOrNull()

    /**
     * Download link for [url] relative to the saved [base] (https origin). Only https on the
     * saved host (and port) is allowed; other hosts, schemes or junk -> null.
     */
    fun resolveDownloadUrl(base: String, url: String): String? = runCatching {
        val baseUri = URI(ServerAddress.normalize(base) ?: return null)
        val target = baseUri.resolve(URI(url.trim()))
        if (!target.scheme.equals("https", ignoreCase = true)) return null
        if (!target.host.equals(baseUri.host, ignoreCase = true)) return null
        val port = if (target.port == 443) -1 else target.port
        val basePort = if (baseUri.port == 443) -1 else baseUri.port
        if (port != basePort) return null
        target.toString()
    }.getOrNull()

    /** Show only for a newer build that the user hasn't already put off with «بعداً». */
    fun shouldNotify(remoteCode: Long, installedCode: Long, dismissedCode: Long): Boolean =
        remoteCode > installedCode && remoteCode > dismissedCode
}
