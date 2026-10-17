package app.myinventory

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.view.View
import androidx.appcompat.app.AlertDialog
import androidx.core.content.edit
import androidx.core.content.pm.PackageInfoCompat
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * «نسخهٔ تازه رسید» notice. Checks <base>/api/app-version at most once per app start,
 * on a background thread with short timeouts; every failure is silent and never delays
 * the app. Texts live in res/values/strings.xml (update_*) so the design is easy to change.
 */
object UpdateNotifier {
    private const val KEY_DISMISSED = "update_dismissed_version_code"
    private const val TIMEOUT_MS = 4000
    private const val MAX_BYTES = 64 * 1024

    @Volatile private var checkedThisProcess = false

    fun checkOnce(activity: Activity, base: String?) {
        if (base == null || checkedThisProcess) return
        checkedThisProcess = true
        val appContext = activity.applicationContext
        thread(name = "update-check", isDaemon = true) {
            try {
                val info = UpdateCheck.parse(fetch("$base/api/app-version")) ?: return@thread
                val download = UpdateCheck.resolveDownloadUrl(base, info.url) ?: return@thread
                val installed = PackageInfoCompat.getLongVersionCode(
                    appContext.packageManager.getPackageInfo(appContext.packageName, 0),
                )
                val dismissed = prefs(appContext).getLong(KEY_DISMISSED, 0L)
                if (!UpdateCheck.shouldNotify(info.versionCode, installed, dismissed)) return@thread
                activity.runOnUiThread { show(activity, info, download) }
            } catch (_: Throwable) {
                // offline, timeout, bad response: stay quiet
            }
        }
    }

    private fun fetch(url: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = TIMEOUT_MS
            conn.readTimeout = TIMEOUT_MS
            conn.instanceFollowRedirects = false
            conn.useCaches = false
            conn.setRequestProperty("Accept", "application/json")
            if (conn.responseCode != 200) return null
            val bytes = conn.inputStream.use { input ->
                val buffer = java.io.ByteArrayOutputStream()
                val chunk = ByteArray(8192)
                while (true) {
                    val n = input.read(chunk)
                    if (n < 0) break
                    buffer.write(chunk, 0, n)
                    if (buffer.size() > MAX_BYTES) return null
                }
                buffer.toByteArray()
            }
            return String(bytes, Charsets.UTF_8)
        } finally {
            conn.disconnect()
        }
    }

    private fun show(activity: Activity, info: UpdateCheck.Info, download: String) {
        if (activity.isFinishing || activity.isDestroyed) return
        val message = buildString {
            append(activity.getString(R.string.update_version_line, info.versionName))
            if (info.notes.isNotEmpty()) {
                append("\n\n")
                append(info.notes.joinToString("\n") { activity.getString(R.string.update_note_bullet, it) })
            }
        }
        val dialog = AlertDialog.Builder(activity)
            .setTitle(R.string.update_title)
            .setMessage(message)
            .setPositiveButton(R.string.update_now) { _, _ -> openDownload(activity, download) }
            .setNegativeButton(R.string.update_later) { _, _ ->
                prefs(activity).edit { putLong(KEY_DISMISSED, info.versionCode) }
            }
            .create()
        dialog.show()
        dialog.window?.decorView?.layoutDirection = View.LAYOUT_DIRECTION_RTL
    }

    /** Hand the APK link to the browser; it downloads and Android's installer takes over. */
    private fun openDownload(activity: Activity, url: String) {
        try {
            activity.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(url)).addCategory(Intent.CATEGORY_BROWSABLE),
            )
        } catch (_: ActivityNotFoundException) {
        }
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
}
