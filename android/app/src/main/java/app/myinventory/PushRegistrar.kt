package app.myinventory

import android.content.Context
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

object PushRegistrar {
    fun registerFcmToken(context: Context) {
        val prefs = context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
        val base = (prefs.getString(MainActivity.KEY_URL, "") ?: "").trimEnd('/')
        if (!base.startsWith("https://")) return
        com.google.firebase.messaging.FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            if (!task.isSuccessful) return@addOnCompleteListener
            val token = task.result ?: return@addOnCompleteListener
            registerToken(context, base, token)
        }
    }

    fun registerToken(@Suppress("UNUSED_PARAMETER") context: Context, base: String, token: String) {
        thread {
            val cookie = readCookie(base) ?: return@thread
            postRegister(base, cookie, token)
        }
    }

    private fun readCookie(base: String): String? {
        val latch = java.util.concurrent.CountDownLatch(1)
        var cookie: String? = null
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            cookie = CookieManager.getInstance().getCookie(base)
            latch.countDown()
        }
        latch.await()
        return cookie
    }

    private fun postRegister(base: String, cookie: String, token: String): Boolean {
        val connection = (URL("$base/api/push/register").openConnection() as HttpURLConnection)
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Cookie", cookie)
        val payload = JSONObject()
        payload.put("token", token)
        payload.put("platform", "android")
        connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        connection.disconnect()
        return code in 200..299
    }
}
