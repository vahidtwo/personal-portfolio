package app.myinventory

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * The raw text of accepted bank SMS, kept on the phone only (app-private file, allowBackup=false) so the date
 * and account can be read later. Never sent to the server. Capped at [MAX_ENTRIES] and [MAX_AGE_MS].
 */
object SmsLog {
    const val MAX_ENTRIES = 200
    const val MAX_AGE_MS = 90L * 24 * 60 * 60 * 1000
    private const val FILE = "sms-log.json"

    data class Entry(val at: Long, val sender: String, val body: String)

    /** Newest last; drops entries older than 90 days (or from the future) and keeps the last 200. */
    fun prune(entries: List<Entry>, now: Long): List<Entry> =
        entries.filter { now - it.at in 0..MAX_AGE_MS }.sortedBy { it.at }.takeLast(MAX_ENTRIES)

    fun toJson(entries: List<Entry>): String = JSONArray(entries.map {
        JSONObject().put("at", it.at).put("sender", it.sender).put("body", it.body)
    }).toString()

    fun fromJson(json: String?): List<Entry> {
        if (json.isNullOrBlank()) return emptyList()
        return runCatching {
            val a = JSONArray(json)
            (0 until a.length()).mapNotNull { i ->
                runCatching { a.getJSONObject(i).let { Entry(it.getLong("at"), it.getString("sender"), it.getString("body")) } }.getOrNull()
            }
        }.getOrDefault(emptyList())
    }

    @Synchronized
    fun append(c: Context, entry: Entry) {
        val f = File(c.filesDir, FILE)
        val current = if (f.exists()) fromJson(runCatching { f.readText() }.getOrNull()) else emptyList()
        val tmp = File(c.filesDir, "$FILE.tmp")
        tmp.writeText(toJson(prune(current + entry, entry.at)))
        if (!tmp.renameTo(f)) { f.delete(); tmp.renameTo(f) }
    }
}
