package app.myinventory

import java.net.URI

/** Address rules for the server box. Pure JVM so it can be unit tested. */
object ServerAddress {
    const val DEFAULT = "https://portfolio.vahidtwo.ir"

    /**
     * Returns the https origin (scheme://host[:port]) for [raw], or null when it can't be used.
     * - blank -> null (callers fall back to [DEFAULT])
     * - no scheme ("portfolio.vahidtwo.ir") -> https:// is added
     * - http:// -> upgraded to https:// (plain http is never loaded)
     * - any other scheme, or no host -> null
     */
    fun normalize(raw: String?): String? {
        var text = raw?.trim().orEmpty()
        if (text.isEmpty()) return null
        if (!Regex("^[A-Za-z][A-Za-z0-9+.-]*://").containsMatchIn(text)) {
            if (Regex("^[A-Za-z][A-Za-z0-9+.-]*:(?!\\d)").containsMatchIn(text)) return null
            text = "https://$text"
        }
        val uri = runCatching { URI(text) }.getOrNull() ?: return null
        val scheme = uri.scheme?.lowercase() ?: return null
        if (scheme != "https" && scheme != "http") return null
        val host = uri.host?.takeIf { it.isNotBlank() }?.lowercase() ?: return null
        val port = uri.port
        val portSuffix = if (port == -1 || port == 443 || port == 80) "" else ":$port"
        return "https://$host$portSuffix"
    }

    /** Like [normalize], but an empty box means the default server. */
    fun normalizeOrDefault(raw: String?): String? =
        if (raw.isNullOrBlank()) DEFAULT else normalize(raw)
}
