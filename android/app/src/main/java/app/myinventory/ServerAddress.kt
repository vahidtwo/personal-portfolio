package app.myinventory

import java.net.URI

/** Address rules for the server box. Pure JVM so it can be unit tested. */
object ServerAddress {
    const val DEFAULT = "https://daraiito.ir"

    /** The v1-v8 default. Still served (same backend) during the move; removed in a later cleanup release. */
    const val OLD_DEFAULT = "https://portfolio.vahidtwo.ir"

    /** Hosts the WebView main frame may open (exact match, https only). */
    val KNOWN_HOSTS = setOf("portfolio.vahidtwo.ir", "daraiito.ir")

    /**
     * Returns the https origin (scheme://host[:port]) for [raw], or null when it can't be used.
     * - blank -> null (callers fall back to [DEFAULT])
     * - no scheme ("daraiito.ir") -> https:// is added
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

    enum class BridgeAction { NAVIGATE, SAVE_ONLY, IGNORE }

    /**
     * What AndroidBridge.setServerUrl may do, given the page that called it.
     * Only the bundled setup page may navigate. A remote page (the site's own
     * android-bridge.js runs on every page) may at most re-save its own https
     * origin; navigating from there caused the v4 reload loop
     * (/dashboard -> landing -> /dashboard ...).
     */
    fun bridgeAction(currentPageUrl: String?, normalizedTarget: String): BridgeAction {
        val page = currentPageUrl.orEmpty()
        if (page.startsWith("file:///android_asset/")) return BridgeAction.NAVIGATE
        val pageOrigin = if (page.startsWith("https://", ignoreCase = true)) normalize(page) else null
        return if (pageOrigin != null && pageOrigin == normalizedTarget) BridgeAction.SAVE_ONLY else BridgeAction.IGNORE
    }

    /**
     * May the main frame open https://[host]? Exact host match against both known hosts
     * and the saved one (a custom address keeps working). No suffix / subdomain match.
     * No saved address yet (setup page) -> any https host, same as v8.
     */
    fun isAllowedRemote(scheme: String?, host: String?, savedBase: String?): Boolean {
        if (scheme?.lowercase() != "https") return false
        val h = host?.lowercase()?.takeIf { it.isNotBlank() } ?: return false
        if (savedBase == null) return true
        if (h in KNOWN_HOSTS) return true
        val savedHost = runCatching { URI(savedBase).host?.lowercase() }.getOrNull() ?: return false
        return h == savedHost
    }

    /**
     * One-time v9 move: only a saved address that is exactly the old default host
     * (any case, http, trailing slash or path) is moved. Custom addresses are never touched.
     */
    fun shouldMigrate(savedRaw: String?, alreadyMigrated: Boolean): Boolean =
        !alreadyMigrated && !savedRaw.isNullOrBlank() && normalize(savedRaw) == OLD_DEFAULT

    /** /health must answer 200 {"ok":true} before we move anyone. */
    fun isHealthOk(code: Int, body: String?): Boolean =
        code == 200 && body != null && Regex("\"ok\"\\s*:\\s*true").containsMatchIn(body)

    /**
     * After the move, if the new host fails to load (connection / SSL) we go back to the old
     * host once, only when the old /health is OK. The flag stops a loop.
     */
    fun shouldFallBack(savedBase: String?, migrated: Boolean, fallbackDone: Boolean, failedUrl: String?): Boolean {
        if (!migrated || fallbackDone) return false
        if (savedBase != DEFAULT) return false
        val failedHost = runCatching { URI(failedUrl ?: return false).host?.lowercase() }.getOrNull()
        return failedHost == "daraiito.ir"
    }

    /**
     * Where an SMS spend is posted: the saved host if it has a session cookie; else the old
     * host when the saved one is the new default and the old host still has a cookie
     * (same backend); else null (don't post, ask the user to log in).
     */
    fun smsTarget(savedBase: String, cookieFor: (String) -> String?): Pair<String, String>? {
        cookieFor(savedBase)?.takeIf { it.isNotBlank() }?.let { return savedBase to it }
        if (savedBase == DEFAULT) {
            cookieFor(OLD_DEFAULT)?.takeIf { it.isNotBlank() }?.let { return OLD_DEFAULT to it }
        }
        return null
    }
}
