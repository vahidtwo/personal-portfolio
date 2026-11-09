package app.myinventory

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

class InventoryMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        PushRegistrar.registerToken(this, baseUrl(), token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.data["title"] ?: message.notification?.title ?: DEFAULT_TITLE
        val body = message.data["body"] ?: message.notification?.body ?: ""
        val path = NotificationTarget.safePath(message.data["url"]) ?: DEFAULT_PATH
        showNotification(title, body, path, message.data["type"] ?: "")
    }

    private fun baseUrl(): String {
        val prefs = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE)
        return (prefs.getString(MainActivity.KEY_URL, "") ?: "").trimEnd('/')
    }

    private fun showNotification(title: String, body: String, path: String, type: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "اعلان‌ها", NotificationManager.IMPORTANCE_DEFAULT),
            )
        }
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_more)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(SmsReceiver.tapIntent(this, path))
            .setAutoCancel(true)
            .build()
        manager.notify((type + title + body).hashCode(), notification)
    }

    companion object {
        const val CHANNEL_ID = "firebase-push"
        const val DEFAULT_TITLE = "دارایی‌تو"
        const val DEFAULT_PATH = "/dashboard"
    }
}
