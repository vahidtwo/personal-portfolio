package app.myinventory

import java.net.URI

/** Address rules for the server box. Pure JVM so it can be unit tested. */
object ServerAddress {
    const val DEFAULT = "https://daraiito.ir"

    /** The v1-v8 default. Still served (same backend) during the move; removed in a later cleanup release. */
    const val OLD_DEFAULT = "https://portfolio.vahidtwo.ir"

    /** Hosts the WebView main frame may open (exact match, https only). */
    val KNOWN_HOSTS = setOf("portfolio.vahidtwo.ir", "daraiito.ir")

    /** Hosts that always open in the external browser, never inside the WebView (exact match, https only). */
    val EXTERNAL_HOSTS = setOf("github.com")

    fun opensExternally(scheme: String?, host: String?): Boolean =
        scheme?.lowercase() == "https" && host?.lowercase() in EXTERNAL_HOSTS

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

    /** After this many fallbacks the move stops retrying (new host keeps failing in the WebView). */
    const val MAX_FALLBACKS = 3

    /**
     * v9 move: only a saved address that is exactly the old default host (any case, http,
     * trailing slash or path) is moved. Custom addresses are never touched. At most one try per
     * cold launch; after a fallback it is tried again on a later launch, up to [MAX_FALLBACKS].
     */
    fun shouldMigrate(
        savedRaw: String?,
        alreadyMigrated: Boolean,
        fallbackCount: Int = 0,
        triedThisLaunch: Boolean = false,
    ): Boolean =
        !alreadyMigrated && !triedThisLaunch && fallbackCount < MAX_FALLBACKS &&
            !savedRaw.isNullOrBlank() && normalize(savedRaw) == OLD_DEFAULT

    /** /health must answer 200 {"ok":true} before we move anyone. */
    fun isHealthOk(code: Int, body: String?): Boolean =
        code == 200 && body != null && Regex("\"ok\"\\s*:\\s*true").containsMatchIn(body)

    /**
     * After the move, if the new host fails to load (connection / SSL) we go back to the old
     * host, at most once per launch. The fallback clears host_migrated so a later launch retries.
     */
    fun shouldFallBack(savedBase: String?, migrated: Boolean, fallbackThisLaunch: Boolean, failedUrl: String?): Boolean {
        if (!migrated || fallbackThisLaunch) return false
        if (savedBase != DEFAULT) return false
        val failedHost = runCatching { URI(failedUrl ?: return false).host?.lowercase() }.getOrNull()
        return failedHost == "daraiito.ir"
    }

    /**
     * Result of `localStorage.getItem("privacy-portfolio")` on the old origin, as WebView's
     * evaluateJavascript returns it (JSON: "\"1\"", "\"0\"", "null"). Hide unless we know for sure
     * amounts were shown: an unreadable result (null callback, timeout, error) hides.
     */
    fun hideAfterMove(jsResult: String?): Boolean = when (jsResult?.trim()) {
        "null", "\"0\"" -> false
        else -> true
    }

    /** First new-host URL after the move; #hide=1 is the #36 hide-only handoff. */
    fun moveTarget(hide: Boolean): String = if (hide) "$DEFAULT/dashboard#hide=1" else "$DEFAULT/dashboard"

    const val SESSION_COOKIE = "inventory_session"
    const val SIGNED_IN_COOKIE = "inventory_signed_in"

    /**
     * A signed-in session, not an anonymous one. The server sets inventory_session for anyone
     * (e.g. the CSRF token on /auth); only signed-in responses also carry inventory_signed_in=1.
     */
    fun hasSignedInSession(cookieHeader: String?): Boolean {
        if (cookieHeader.isNullOrBlank()) return false
        val pairs = cookieHeader.split(';').mapNotNull {
            val i = it.indexOf('=')
            if (i <= 0) null else it.substring(0, i).trim() to it.substring(i + 1).trim()
        }.toMap()
        return pairs[SIGNED_IN_COOKIE] == "1" && !pairs[SESSION_COOKIE].isNullOrEmpty()
    }

    /**
     * Where an SMS spend is posted: the saved host if it has a signed-in session; else the old
     * host when the saved one is the new default and the old host still has one (same backend);
     * else null (don't post, ask the user to log in).
     */
    fun smsTarget(savedBase: String, cookieFor: (String) -> String?): Pair<String, String>? {
        cookieFor(savedBase)?.takeIf { hasSignedInSession(it) }?.let { return savedBase to it }
        if (savedBase == DEFAULT) {
            cookieFor(OLD_DEFAULT)?.takeIf { hasSignedInSession(it) }?.let { return OLD_DEFAULT to it }
        }
        return null
    }

    enum class SmsOutcome { SAVED, LOGIN_NEEDED, FAILED }

    /** HTTP code (null = network error / exception) -> what we tell the user. */
    fun smsOutcome(code: Int?): SmsOutcome = when {
        code == null -> SmsOutcome.FAILED
        code in 200..299 -> SmsOutcome.SAVED
        code == 401 || code == 403 -> SmsOutcome.LOGIN_NEEDED
        else -> SmsOutcome.FAILED
    }

    /**
     * Cold launch on the moved-to new host that is not confirmed yet: probe /health natively
     * first, because daraiito.ir's service worker answers a dead network with its cached offline
     * page and the WebView then reports no error. Once per launch.
     */
    fun shouldProbeOnLaunch(savedBase: String?, migrated: Boolean, confirmed: Boolean, probedThisLaunch: Boolean): Boolean =
        savedBase == DEFAULT && migrated && !confirmed && !probedThisLaunch

    /** Marker in /offline.html (<meta name="x-offline" content="1">). */
    const val OFFLINE_MARKER_JS =
        "(function(){var m=document.querySelector('meta[name=\"x-offline\"]');return m&&m.content==='1'?'1':'0'})()"

    /** evaluateJavascript result of [OFFLINE_MARKER_JS]: only an exact "1" is the offline page. */
    fun isOfflinePage(jsResult: String?): Boolean = jsResult?.trim() == "\"1\""
}
