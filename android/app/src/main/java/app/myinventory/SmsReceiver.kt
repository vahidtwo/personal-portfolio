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
        val templates = SmsPrefs.templates(context)
        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        val body = messages.joinToString("") { it.displayMessageBody ?: "" }
        val sender = messages.firstOrNull()?.originatingAddress ?: ""
        // One SMS → at most one spend.
        val spend = SmsDecision.decide(body, sender, keywords, templates) ?: return
        val amount = spend.amountToman
        val note = spend.note
        val pending = goAsync()
        val idem = sha256("$sender|$body")
        val entry = SmsQueue.Entry(amount, note, idem, System.currentTimeMillis())
        thread {
            try {
                runCatching { SmsLog.append(context, SmsLog.Entry(System.currentTimeMillis(), sender, body)) }
                    .onFailure { Log.w(TAG, "sms: local log failed", it) }
                // v9: signed-in session on the saved host first; else the old host's (same backend).
                val target = ServerAddress.smsTarget(base) { readCookie(it) }
                val outcome = if (target == null) {
                    Log.i(TAG, "sms: no signed-in session")
                    ServerAddress.SmsOutcome.LOGIN_NEEDED
                } else {
                    val code = runCatching { SmsQueue.post(target.first, target.second, SmsQueue.payload(entry)) }
                        .onFailure { Log.w(TAG, "sms: post failed", it) }.getOrNull()
                    Log.i(TAG, "sms: post code=$code")
                    ServerAddress.smsOutcome(code)
                }
                when (outcome) {
                    ServerAddress.SmsOutcome.SAVED -> notifySaved(context, amount)
                    ServerAddress.SmsOutcome.LOGIN_NEEDED -> {
                        // Kept (encrypted, app-private) until a login succeeds, then sent with the same key.
                        runCatching { SmsQueue.add(context, entry) }.onFailure { Log.w(TAG, "sms: queue failed", it) }
                        // Shown in the app on next open too, in case notifications are off.
                        prefs.edit().putBoolean(KEY_LOGIN_NEEDED, true).apply()
                        notify(context, "خرج پیامک", LOGIN_MESSAGE, HomeActivity::class.java)
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
        const val LOGIN_MESSAGE = "وارد نشده‌اید — خرج بعد از ورود ذخیره می‌شود"

        /** Sends spends queued while signed out, if a session exists now. Safe to call often. */
        fun flushQueued(context: Context) {
            val app = context.applicationContext
            thread {
                runCatching {
                    if (SmsQueue.size(app) == 0) return@thread
                    val prefs = app.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
                    val base = (prefs.getString(MainActivity.KEY_URL, "") ?: "").trimEnd('/')
                    if (base.isEmpty()) return@thread
                    val target = ServerAddress.smsTarget(base) { readCookieOnMain(it) } ?: return@thread
                    val saved = SmsQueue.flush(app, target.first, target.second)
                    Log.i(TAG, "sms: flushed $saved")
                    if (saved > 0) {
                        prefs.edit().putBoolean(KEY_LOGIN_NEEDED, false).apply()
                        notify(app, "خرج‌های پیامکی ذخیره شد", "$saved خرج بعد از ورود ذخیره شد", null)
                    }
                }.onFailure { Log.w(TAG, "sms: flush failed", it) }
            }
        }

        private fun readCookieOnMain(base: String): String? {
            if (Looper.myLooper() == Looper.getMainLooper()) return CookieManager.getInstance().getCookie(base)
            val latch = java.util.concurrent.CountDownLatch(1)
            var cookie: String? = null
            Handler(Looper.getMainLooper()).post {
                cookie = CookieManager.getInstance().getCookie(base)
                latch.countDown()
            }
            latch.await(5, java.util.concurrent.TimeUnit.SECONDS)
            return cookie
        }

        internal fun notify(context: Context, title: String, text: String, tap: Class<*>?) {
            if (Build.VERSION.SDK_INT >= 33 &&
                ContextCompat.checkSelfPermission(context, android.Manifest.permission.POST_NOTIFICATIONS)
                != android.content.pm.PackageManager.PERMISSION_GRANTED
            ) return
            val manager = context.getSystemService(NotificationManager::class.java)
            if (Build.VERSION.SDK_INT >= 26) {
                manager.createNotificationChannel(
                    NotificationChannel("sms-spend", "خرج پیامک", NotificationManager.IMPORTANCE_DEFAULT)
                )
            }
            val b = NotificationCompat.Builder(context, "sms-spend")
                .setSmallIcon(android.R.drawable.stat_notify_more)
                .setContentTitle(title).setContentText(text).setAutoCancel(true)
            if (tap != null) {
                val pi = android.app.PendingIntent.getActivity(context, 0,
                    android.content.Intent(context, tap).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK),
                    android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT)
                b.setContentIntent(pi)
            }
            manager.notify(text.hashCode(), b.build())
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
