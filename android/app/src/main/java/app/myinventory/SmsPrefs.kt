package app.myinventory

import android.Manifest
import android.content.Context
import android.content.SharedPreferences
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.core.content.edit

/** On-device SMS settings. Keywords are never sent to the server (allowBackup=false too). */
object SmsPrefs {
    const val KEY_KEYWORDS = "sms_keywords"
    const val KEY_ENABLED = "sms_enabled"
    const val KEY_UPGRADE_NOTE = "sms_upgrade_note_pending"
    const val KEY_ASKED = "sms_permission_asked"

    private fun prefs(c: Context): SharedPreferences =
        c.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)

    fun permissionGranted(c: Context): Boolean =
        ContextCompat.checkSelfPermission(c, Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED

    /** v5 → v6, runs once. Idempotent. */
    @Synchronized
    fun ensureMigrated(c: Context) {
        val p = prefs(c)
        val m = SmsKeywords.migrate(
            p.getString(KEY_KEYWORDS, null),
            p.contains(MainActivity.KEY_PHRASE),
            p.getString(MainActivity.KEY_PHRASE, null),
        )
        p.edit {
            if (m != null) {
                putString(KEY_KEYWORDS, SmsKeywords.toJson(m.keywords))
                if (m.showUpgradeNote) putBoolean(KEY_UPGRADE_NOTE, true)
            }
            // v5 asked for SMS at launch; keep it working for people who granted it.
            if (!p.contains(KEY_ENABLED)) putBoolean(KEY_ENABLED, permissionGranted(c))
        }
    }

    fun keywords(c: Context): List<String> {
        ensureMigrated(c)
        return SmsKeywords.fromJson(prefs(c).getString(KEY_KEYWORDS, null)).ifEmpty { listOf(SmsKeywords.DEFAULT) }
    }

    /** Storage-level guard: never writes an empty list. */
    fun saveKeywords(c: Context, list: List<String>) {
        require(list.isNotEmpty()) { "at least one keyword is required" }
        prefs(c).edit { putString(KEY_KEYWORDS, SmsKeywords.toJson(list)) }
    }

    fun isEnabledPref(c: Context): Boolean { ensureMigrated(c); return prefs(c).getBoolean(KEY_ENABLED, false) }
    fun setEnabled(c: Context, on: Boolean) = prefs(c).edit { putBoolean(KEY_ENABLED, on) }
    /** Active = user switched it on AND Android permission granted. */
    fun isActive(c: Context): Boolean = isEnabledPref(c) && permissionGranted(c)

    fun upgradeNotePending(c: Context): Boolean { ensureMigrated(c); return prefs(c).getBoolean(KEY_UPGRADE_NOTE, false) }
    fun dismissUpgradeNote(c: Context) = prefs(c).edit { putBoolean(KEY_UPGRADE_NOTE, false) }
    fun askedBefore(c: Context): Boolean = prefs(c).getBoolean(KEY_ASKED, false)
    fun markAsked(c: Context) = prefs(c).edit { putBoolean(KEY_ASKED, true) }
}
