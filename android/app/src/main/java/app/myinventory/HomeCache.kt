package app.myinventory

import android.content.Context
import org.json.JSONObject
import java.io.File

/**
 * Version-keyed cache of the last /api/home payload. The key is app versionCode + the per-user
 * inventory_page_key, so an app update or another account never sees an old copy. Fonts and the logo are
 * APK resources, so they are version-keyed by the APK itself. Logout deletes the file.
 */
class HomeCache(private val context: Context) {
    private val file: File get() = File(context.filesDir, "home-cache.json")

    fun read(key: String?): Pair<JSONObject, Long>? {
        if (key == null) return null
        val f = file
        if (!f.isFile) return null
        val root = runCatching { JSONObject(f.readText()) }.getOrNull() ?: return null
        if (root.optString("key") != key) return null
        val data = root.optJSONObject("data") ?: return null
        return data to root.optLong("saved_at")
    }

    fun write(key: String?, data: JSONObject, now: Long) {
        if (key == null) return
        val root = JSONObject().put("key", key).put("saved_at", now).put("data", data)
        val tmp = File(context.filesDir, "home-cache.json.tmp")
        tmp.writeText(root.toString())
        tmp.renameTo(file)
    }

    fun clear() {
        file.delete()
    }

    companion object {
        fun key(versionCode: Int, pageKey: String?): String? =
            if (pageKey.isNullOrEmpty()) null else "v$versionCode:$pageKey"
    }
}
