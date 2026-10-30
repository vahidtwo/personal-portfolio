package app.myinventory

import android.webkit.CookieManager
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * HTTP for the native screens. The WebView CookieManager is the only cookie store, so a native login is the
 * WebView session too (inventory_session, inventory_signed_in=1, inventory_page_key come from the server as-is).
 */
object NativeSession {
    val BASE: String = BuildConfig.APP_BASE
    const val MARKER = "inventory_signed_in"
    const val PAGE_KEY = "inventory_page_key"
    private const val TIMEOUT_MS = 8000

    class Response(val status: Int, val json: JSONObject, val retryAfter: Int)

    private var csrf: String? = null

    fun cookie(name: String): String? = CookieJar.value(CookieManager.getInstance().getCookie(BASE), name)

    fun signedIn(): Boolean = cookie(MARKER) == "1"

    @Throws(IOException::class)
    fun request(method: String, path: String, body: JSONObject? = null, withCsrf: Boolean = false): Response {
        val conn = URL(BASE + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = TIMEOUT_MS
            conn.readTimeout = TIMEOUT_MS
            conn.instanceFollowRedirects = false
            conn.useCaches = false
            conn.setRequestProperty("Accept", "application/json")
            conn.setRequestProperty("X-Requested-With", "app.daraiito")
            CookieManager.getInstance().getCookie(BASE)?.let { conn.setRequestProperty("Cookie", it) }
            if (withCsrf) conn.setRequestProperty("X-CSRF-Token", csrf ?: "")
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val status = conn.responseCode
            storeCookies(conn)
            val stream = if (status >= 400) conn.errorStream else conn.inputStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            val json = runCatching { JSONObject(text) }.getOrDefault(JSONObject())
            return Response(status, json, conn.getHeaderField("Retry-After")?.toIntOrNull() ?: 0)
        } finally {
            conn.disconnect()
        }
    }

    private fun storeCookies(conn: HttpURLConnection) {
        val cm = CookieManager.getInstance()
        conn.headerFields.forEach { (k, values) ->
            if (k != null && k.equals("Set-Cookie", ignoreCase = true)) values.forEach { cm.setCookie(BASE, it) }
        }
        cm.flush()
    }

    @Throws(IOException::class)
    fun refreshCsrf() {
        csrf = request("GET", "/api/auth/csrf").json.optString("csrf").takeIf { it.isNotEmpty() }
    }

    /** POST with the session-bound CSRF token; a stale token (400) is refreshed once. */
    @Throws(IOException::class)
    fun post(path: String, body: JSONObject): Response {
        if (csrf == null) refreshCsrf()
        var r = request("POST", path, body, withCsrf = true)
        if (r.status == 400 && r.json.optString("result").isEmpty()) {
            refreshCsrf()
            r = request("POST", path, body, withCsrf = true)
        }
        return r
    }

    /** Drop the session from the WebView cookie store too (server cookies may already be gone). */
    fun clearLocal() {
        csrf = null
        val cm = CookieManager.getInstance()
        for (name in listOf("inventory_session", MARKER, PAGE_KEY)) {
            cm.setCookie(BASE, "$name=; Max-Age=0; Path=/")
        }
        cm.flush()
    }
}

/** Cookie header parsing (pure, unit tested). */
object CookieJar {
    fun value(header: String?, name: String): String? {
        if (header.isNullOrEmpty()) return null
        return header.split(';').map { it.trim() }.firstOrNull { it.startsWith("$name=") }?.substringAfter('=')
    }
}
