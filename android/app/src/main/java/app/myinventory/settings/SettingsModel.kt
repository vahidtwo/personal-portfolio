package app.myinventory.settings

import org.json.JSONObject

/** What GET /api/settings returns. Nothing about the salary, not even whether one is saved. */
data class SettingsData(
    val fullName: String,
    val username: String,
    val mobile: String,
    val isAdmin: Boolean,
)

/** Result of a settings write: ok with the saved copy, or field errors in the server's own words. */
data class WriteResult(val ok: Boolean, val title: String, val detail: String, val errors: Map<String, String>, val json: JSONObject)

/** Pure parsing and display rules for the settings tab (unit tested). */
object SettingsModel {
    fun parse(json: JSONObject): SettingsData? {
        val account = json.optJSONObject("account") ?: return null
        return SettingsData(
            fullName = account.optString("full_name"),
            username = account.optString("username"),
            mobile = account.optString("mobile"),
            isAdmin = json.optBoolean("is_admin"),
        )
    }

    fun withAccount(data: SettingsData, json: JSONObject): SettingsData {
        val a = json.optJSONObject("account") ?: return data
        return data.copy(fullName = a.optString("full_name"), username = a.optString("username"), mobile = a.optString("mobile"))
    }

    fun writeResult(status: Int, json: JSONObject): WriteResult {
        val errors = mutableMapOf<String, String>()
        json.optJSONObject("errors")?.let { e -> e.keys().forEach { k -> errors[k] = e.optString(k) } }
        val ok = status == 200 && json.optBoolean("ok")
        return WriteResult(ok, json.optString("title"), json.optString("detail"), errors, json)
    }

    /** First letter for the avatar: the name, else the username, else «؟». */
    fun avatarLetter(fullName: String, username: String): String =
        (fullName.trim().ifEmpty { username.trim() }).firstOrNull()?.uppercaseChar()?.toString() ?: "؟"

    /** «۴۵٬۰۰۰٬۰۰۰ تومان» → («۴۵٬۰۰۰٬۰۰۰», «تومان»). Anything without a number means none saved. */
    fun salaryParts(label: String): Pair<String, String>? {
        val t = label.trim()
        if (t.none { it.isDigit() }) return null
        val unit = "تومان"
        return if (t.endsWith(unit)) t.removeSuffix(unit).trim() to unit else t to unit
    }

    /** A revealed salary of zero means none is saved yet. */
    fun salaryIsNone(number: String): Boolean = number.none { it.isDigit() && it != '0' && it != '۰' }

    /** «12.1.7» → «۱۲٫۱٫۷». */
    fun versionLabel(name: String, faDigits: (String) -> String): String = faDigits(name).replace('.', '٫')

    /** A username change needs the current password (same rule as the web form). */
    fun needsCurrentPassword(original: String, typed: String): Boolean =
        typed.trim().lowercase() != original.trim().lowercase()

    /** Trailing text of the SMS row. */
    fun smsTrailing(active: Boolean, keywords: Int, faDigits: (String) -> String): String =
        if (active) "روشن، ${faDigits(keywords.toString())} کلمه" else "خاموش"
}
