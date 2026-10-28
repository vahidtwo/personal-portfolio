package app.myinventory

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Telephony
import android.util.Log
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
        if (!base.startsWith("https://")) return
        if (!SmsPrefs.isActive(context)) return
        val keywords = SmsPrefs.keywords(context)
        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        val body = messages.joinToString("") { it.displayMessageBody ?: "" }
        val sender = messages.firstOrNull()?.originatingAddress ?: ""
        // One SMS → at most one spend, however many keywords it contains.
        val amount = SmsKeywords.spendAmount(body, keywords) ?: return
        val pending = goAsync()
        val idem = sha256("$sender|$body")
        thread {
            try {
                val note = SmsKeywords.cleanNote(body)
                // v9: signed-in session on the saved host first; else the old host's (same backend).
                val target = ServerAddress.smsTarget(base) { readCookie(it) }
                val outcome = if (target == null) {
                    Log.i(TAG, "sms: no signed-in session")
                    ServerAddress.SmsOutcome.LOGIN_NEEDED
                } else {
                    val code = runCatching { postSpend(target.first, target.second, amount, note, idem) }
                        .onFailure { Log.w(TAG, "sms: post failed", it) }.getOrNull()
                    Log.i(TAG, "sms: post code=$code")
                    ServerAddress.smsOutcome(code)
                }
                when (outcome) {
                    ServerAddress.SmsOutcome.SAVED -> notifySaved(context, amount)
                    ServerAddress.SmsOutcome.LOGIN_NEEDED -> {
                        // Shown in the app on next open too, in case notifications are off.
                        prefs.edit().putBoolean(KEY_LOGIN_NEEDED, true).apply()
                        notifyError(context, LOGIN_MESSAGE)
                    }
                    ServerAddress.SmsOutcome.FAILED -> notifyError(context, "ذخیره نشد — سرور در دسترس نیست")
                }
            } catch (t: Throwable) {
                // Never die silently in the background thread (that crashed the process with no notice).
                Log.w(TAG, "sms: unexpected", t)
                runCatching { notifyError(context, "ذخیره نشد — سرور در دسترس نیست") }
            } finally {
                pending.finish()
            }
        }
    }

    companion object {
        private const val TAG = "SmsReceiver"
        const val KEY_LOGIN_NEEDED = "sms_login_needed"
        const val LOGIN_MESSAGE = "وارد نشده‌اید — در اپ لاگین کنید"
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


    private fun postSpend(base: String, cookie: String, amount: String, note: String, idem: String): Int {
        val connection = (URL("$base/api/sms-spend").openConnection() as HttpURLConnection)
        connection.requestMethod = "POST"
        connection.instanceFollowRedirects = false
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
        return code
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
