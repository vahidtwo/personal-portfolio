package app.myinventory

import org.json.JSONArray
import org.json.JSONObject
import java.net.URI
import java.util.Locale

/** Pure logic for the update notice (unit tested; no Android APIs). */
object UpdateCheck {
    const val SNOOZE_MS = 24L * 60 * 60 * 1000
    const val MAX_NOTES = 4

    /** False in the store flavor: the store delivers updates (no check, download or install prompt). */
    val inAppUpdatesEnabled: Boolean get() = BuildConfig.IN_APP_UPDATES

    data class Info(
        val versionCode: Long,
        val versionName: String,
        val url: String,
        val sha256: String?,
        val sizeBytes: Long?,
        val certSha256: String?,
        val notes: List<String>,
        /** Parsed but deliberately ignored: forced updates are not approved. */
        val minRequired: Long = 0,
    )

    private fun asLong(v: Any?): Long? = when (v) {
        is Int -> v.toLong()
        is Long -> v
        else -> null
    }

    private fun hex64(v: Any?): String? =
        (v as? String)?.lowercase(Locale.ROOT)?.takeIf { Regex("[0-9a-f]{64}").matches(it) }

    /** Parses /api/app-version. Anything malformed or of the wrong type -> null. */
    fun parse(body: String?): Info? = runCatching {
        val obj = JSONObject(body ?: return null)
        val versionCode = asLong(obj.opt("versionCode")) ?: return null
        if (versionCode <= 0) return null
        val name = obj.opt("versionName") as? String ?: return null
        val url = obj.opt("url") as? String ?: return null
        val notes = when (val raw = obj.opt("notes")) {
            null, JSONObject.NULL -> emptyList()
            is JSONArray -> (0 until raw.length()).mapNotNull { (raw.opt(it) as? String)?.trim()?.takeIf(String::isNotEmpty) }
            else -> return null
        }.take(MAX_NOTES)
        Info(
            versionCode = versionCode,
            versionName = name,
            url = url,
            sha256 = hex64(obj.opt("sha256")),
            sizeBytes = asLong(obj.opt("size_bytes"))?.takeIf { it > 0 },
            certSha256 = hex64(obj.opt("cert_sha256")),
            notes = notes,
            minRequired = asLong(obj.opt("min_required")) ?: 0L,
        )
    }.getOrNull()

    /**
     * Download link for [url] resolved against [checkBase] (where /api/app-version came from).
     * The result must be on the same host and port as [checkBase] and use https. Only when
     * [httpAllowedHost] is set (QA build: "10.0.2.2") may that exact host use plain http.
     */
    fun resolveDownloadUrl(checkBase: String, url: String, httpAllowedHost: String? = null): String? = runCatching {
        val base = URI(checkBase.trim())
        if (!isAllowedScheme(base, httpAllowedHost)) return null
        val target = base.resolve(URI(url.trim()))
        if (!isAllowedScheme(target, httpAllowedHost)) return null
        if (target.host.isNullOrEmpty() || !target.host.equals(base.host, ignoreCase = true)) return null
        if (effectivePort(target) != effectivePort(base)) return null
        if (!target.scheme.equals(base.scheme, ignoreCase = true)) return null
        target.toString()
    }.getOrNull()

    private fun isAllowedScheme(uri: URI, httpAllowedHost: String?): Boolean {
        val scheme = uri.scheme?.lowercase(Locale.ROOT) ?: return false
        if (uri.host.isNullOrEmpty()) return false
        return scheme == "https" ||
            (scheme == "http" && !httpAllowedHost.isNullOrEmpty() && uri.host.equals(httpAllowedHost, ignoreCase = true))
    }

    private fun effectivePort(uri: URI): Int = when {
        uri.port != -1 -> uri.port
        uri.scheme.equals("https", ignoreCase = true) -> 443
        else -> 80
    }

    /**
     * Show only for a newer build. «بعداً» (stored as wall-clock [dismissedAtMs] plus the
     * [dismissedCode] it was for) keeps it quiet for 24 h, unless an even newer build appears.
     * A dismissal "in the future" (clock moved back) is treated as expired, so it never
     * silences the notice forever.
     */
    fun shouldNotify(
        remoteCode: Long,
        installedCode: Long,
        dismissedCode: Long,
        dismissedAtMs: Long,
        nowMs: Long,
    ): Boolean {
        if (remoteCode <= installedCode) return false
        if (remoteCode > dismissedCode) return true
        val elapsed = nowMs - dismissedAtMs
        return elapsed < 0 || elapsed >= SNOOZE_MS
    }

    /**
     * The notice may only appear on the dashboard (/dashboard, any query): https on the saved
     * host. Every other page (landing, auth, profile, assets, spends...) and the local file
     * pages (setup, loading, error, advanced) never qualify.
     */
    fun isEligiblePage(pageUrl: String?, savedBase: String?): Boolean = runCatching {
        if (pageUrl == null || savedBase == null) return false
        val page = URI(pageUrl)
        val base = URI(savedBase)
        if (!page.scheme.equals("https", ignoreCase = true)) return false
        if (!page.host.equals(base.host, ignoreCase = true)) return false
        val path = (page.path ?: "").trimEnd('/')
        path == "/dashboard"
    }.getOrNull() ?: false

    // ---- Persian formatting («٫» decimal, «٪», Persian digits) ----

    fun fa(text: String): String = buildString {
        for (c in text) append(if (c in '0'..'9') '۰' + (c - '0') else if (c == '.') '٫' else c)
    }

    /** «حدود ۳ مگابایت»: whole megabytes, at least 1. */
    fun sizeAbout(sizeBytes: Long?): String? {
        if (sizeBytes == null || sizeBytes <= 0) return null
        val mb = maxOf(1L, Math.round(sizeBytes / (1024.0 * 1024.0)))
        return "حدود ${fa(mb.toString())} مگابایت"
    }

    /** «۶۲٪» */
    fun percent(done: Long, total: Long): String =
        fa(percentValue(done, total).toString()) + "٪"

    fun percentValue(done: Long, total: Long): Int =
        if (total <= 0) 0 else ((done * 100) / total).toInt().coerceIn(0, 100)

    /** «۱٫۹ از ۳٫۱ مگابایت» */
    fun progressMb(done: Long, total: Long): String {
        fun mb(v: Long) = fa(String.format(Locale.ROOT, "%.1f", v / (1024.0 * 1024.0)))
        return if (total > 0) "${mb(done)} از ${mb(total)} مگابایت" else "${mb(done)} مگابایت"
    }
}
