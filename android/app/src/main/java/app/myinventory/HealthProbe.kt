package app.myinventory

import java.net.HttpURLConnection
import java.net.URL

/** GET {base}/health, expects 200 {"ok":true}. Short timeouts, no redirects. Call off the UI thread. */
object HealthProbe {
    const val TIMEOUT_MS = 3500

    fun isUp(base: String, timeoutMs: Int = TIMEOUT_MS): Boolean = runCatching {
        val c = URL("$base/health").openConnection() as HttpURLConnection
        c.instanceFollowRedirects = false
        c.connectTimeout = timeoutMs
        c.readTimeout = timeoutMs
        try {
            val code = c.responseCode
            val body = if (code == 200) c.inputStream.bufferedReader().use { it.readText().take(200) } else null
            ServerAddress.isHealthOk(code, body)
        } finally {
            c.disconnect()
        }
    }.getOrDefault(false)
}
