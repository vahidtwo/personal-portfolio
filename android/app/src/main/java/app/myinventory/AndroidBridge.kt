package app.myinventory

import android.content.Context
import android.webkit.JavascriptInterface
import androidx.core.content.edit

class AndroidBridge(
    private val context: Context,
    private val onServerConfigured: (String) -> Unit,
) {
    /** Returns false when the address is rejected (empty, not https, or no host). */
    @JavascriptInterface
    fun setServerUrl(url: String): Boolean {
        val normalized = normalizeBaseUrl(url) ?: return false
        context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE).edit {
            putString(MainActivity.KEY_URL, normalized)
        }
        onServerConfigured(normalized)
        return true
    }

    @JavascriptInterface
    fun getServerUrl(): String {
        return context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
            .getString(MainActivity.KEY_URL, "") ?: ""
    }

    @JavascriptInterface
    fun setSmsPhrase(phrase: String) {
        val value = phrase.trim().ifEmpty { MainActivity.DEFAULT_PHRASE }
        context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE).edit {
            putString(MainActivity.KEY_PHRASE, value)
        }
    }

    @JavascriptInterface
    fun getSmsPhrase(): String {
        val prefs = context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
        return prefs.getString(MainActivity.KEY_PHRASE, MainActivity.DEFAULT_PHRASE)
            ?: MainActivity.DEFAULT_PHRASE
    }

    @JavascriptInterface
    fun isAndroidApp(): Boolean = true

    companion object {
        fun normalizeBaseUrl(raw: String): String? {
            val trimmed = raw.trim()
            if (trimmed.isEmpty()) return null
            val uri = android.net.Uri.parse(trimmed)
            if (uri.scheme != "https" || uri.host.isNullOrBlank()) return null
            return "https://${uri.host}"
        }
    }
}
