package app.myinventory

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Telephony
import android.webkit.CookieManager
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlin.concurrent.thread

class SmsReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(context: Context, intent: android.content.Intent) {
        if (Telephony.Sms.Intents.SMS_RECEIVED_ACTION != intent.action) return
        val prefs = context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
        val base = (prefs.getString(MainActivity.KEY_URL, "") ?: "").trimEnd('/')
        val phrase = prefs.getString(MainActivity.KEY_PHRASE, MainActivity.DEFAULT_PHRASE)
            ?: MainActivity.DEFAULT_PHRASE
        if (!base.startsWith("https://")) return
        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        val body = messages.joinToString("") { it.displayMessageBody ?: "" }
        val sender = messages.firstOrNull()?.originatingAddress ?: ""
        if (phrase.isNotEmpty() && !body.contains(phrase)) return
        val amount = parseAmount(body) ?: return
        val pending = goAsync()
        val idem = sha256("$sender|$body")
        thread {
            try {
                val note = body.replace("\n", " ").take(100)
                val cookie = readCookie(base)
                if (cookie.isNullOrBlank()) {
                    notifyError(context, "وارد نشده‌اید — در اپ لاگین کنید")
                    return@thread
                }
                val ok = postSpend(base, cookie, amount, note, idem)
                if (ok) notifySaved(context, amount) else notifyError(context, "ذخیره نشد — سرور در دسترس نیست")
            } finally {
                pending.finish()
            }
        }
    }

    private fun readCookie(base: String): String? {
        val latch = java.util.concurrent.CountDownLatch(1)
        var cookie: String? = null
        Handler(Looper.getMainLooper()).post {
            cookie = CookieManager.getInstance().getCookie(base)
            latch.countDown()
        }
        latch.await()
        return cookie
    }

    private fun sha256(text: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }
    }

    private fun parseAmount(body: String): String? {
        val normalized = body.map { ch ->
            when (ch) {
                in '۰'..'۹' -> '0' + (ch - '۰')
                in '٠'..'٩' -> '0' + (ch - '٠')
                else -> ch
            }
        }.joinToString("")
        val patterns = listOf(
            Regex("""(?:مبلغ|برداشت|withdraw)[^\d]{0,20}(\d[\d,]*)""", RegexOption.IGNORE_CASE),
            Regex("""(\d[\d,]{3,})\s*(?:ریال|تومان|Rial|Toman)""", RegexOption.IGNORE_CASE),
        )
        val raw = patterns.firstNotNullOfOrNull { it.find(normalized)?.groupValues?.get(1) } ?: return null
        val digits = raw.replace(",", "")
        val value = digits.toLongOrNull() ?: return null
        if (value <= 0) return null
        val lower = body.lowercase()
        val rial = (lower.contains("ریال") || lower.contains("rial")) && !lower.contains("تومان") && !lower.contains("toman")
        val toman = if (rial) value / 10 else value
        if (toman <= 0) return null
        return toman.toString()
    }

    private fun postSpend(base: String, cookie: String, amount: String, note: String, idem: String): Boolean {
        val connection = (URL("$base/api/sms-spend").openConnection() as HttpURLConnection)
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Cookie", cookie)
        val payload = JSONObject()
        payload.put("amount_toman", amount)
        payload.put("note", note)
        payload.put("idempotency_key", idem)
        connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        connection.disconnect()
        return code in 200..299
    }

    private fun notifySaved(context: Context, amount: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS)
            != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel("sms-spend", "خرج پیامک", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
        val notification = NotificationCompat.Builder(context, "sms-spend")
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("خرج روزانه ذخیره شد")
            .setContentText(amount)
            .build()
        manager.notify(amount.hashCode(), notification)
    }

    private fun notifyError(context: Context, message: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ActivityCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS)
            != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        val manager = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel("sms-spend", "خرج پیامک", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
        val notification = NotificationCompat.Builder(context, "sms-spend")
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle("خرج پیامک")
            .setContentText(message)
            .build()
        manager.notify(message.hashCode(), notification)
    }
}
