package app.myinventory

import org.json.JSONObject

/**
 * Firebase client values for this Android app, read from the server's /api/push/config at runtime
 * (the APK carries no google-services.json). All four are public client identifiers, not secrets.
 */
data class PushOptions(val appId: String, val apiKey: String, val projectId: String, val senderId: String) {
    fun toJson(): String = JSONObject()
        .put("appId", appId).put("apiKey", apiKey).put("projectId", projectId).put("senderId", senderId)
        .toString()

    companion object {
        private val APP_ID = Regex("^1:([0-9]+):android:[0-9a-f]+$")
        private val PROJECT_ID = Regex("^[a-z0-9-]{4,64}$")
        private val API_KEY = Regex("^[A-Za-z0-9_-]{20,64}$")

        /** The `android` object of /api/push/config (or that object alone, as cached); null when unusable. */
        fun fromJson(raw: String?): PushOptions? {
            if (raw.isNullOrBlank()) return null
            val root = runCatching { JSONObject(raw) }.getOrNull() ?: return null
            val o = root.optJSONObject("android") ?: if (root.has("appId")) root else return null
            val appId = o.optString("appId").trim()
            val apiKey = o.optString("apiKey").trim()
            val projectId = o.optString("projectId").trim()
            val senderId = o.optString("senderId").trim()
            val m = APP_ID.matchEntire(appId) ?: return null
            if (m.groupValues[1] != senderId) return null
            if (!PROJECT_ID.matches(projectId) || !API_KEY.matches(apiKey)) return null
            return PushOptions(appId, apiKey, projectId, senderId)
        }
    }
}

/** What the settings page shows after «فعال‌سازی اعلان» in the app (AndroidBridge.pushState). */
object PushState {
    const val IDLE = "idle"
    const val PENDING = "pending"
    const val OK = "ok"
    const val UNCONFIGURED = "unconfigured"
    const val LOGIN = "login"
    const val TOKEN_FAILED = "token-failed"
    const val REGISTER_FAILED = "register-failed"

    /** Re-send the same token at most this often unless the user asks (settings button) or it changed. */
    const val REREGISTER_MS = 12L * 60 * 60 * 1000

    fun shouldRegister(force: Boolean, token: String, lastToken: String?, lastAt: Long, now: Long): Boolean =
        force || token != lastToken || now - lastAt !in 0 until REREGISTER_MS

    fun stateForHttp(code: Int): String = when (code) {
        in 200..299 -> OK
        401 -> LOGIN
        else -> REGISTER_FAILED
    }

    fun json(permission: String, state: String, detail: String): String =
        JSONObject().put("permission", permission).put("state", state).put("detail", detail).toString()
}
