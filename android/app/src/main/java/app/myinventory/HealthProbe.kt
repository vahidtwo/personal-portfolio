package app.myinventory

import java.net.HttpURLConnection
import java.net.URL

/** GET {base}/health, expects 200 {"ok":true}. Short timeouts, no redirects. Call off the UI thread. */
object HealthProbe {
    fun isUp(base: String): Boolean = runCatching {
        val c = URL("$base/health").openConnection() as HttpURLConnection
        c.instanceFollowRedirects = false
        c.connectTimeout = 5000
        c.readTimeout = 5000
        try {
            val code = c.responseCode
            val body = if (code == 200) c.inputStream.bufferedReader().use { it.readText().take(200) } else null
            ServerAddress.isHealthOk(code, body)
        } finally {
            c.disconnect()
        }
    }.getOrDefault(false)
}
