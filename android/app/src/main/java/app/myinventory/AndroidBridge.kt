package app.myinventory

import android.content.Context
import android.webkit.JavascriptInterface
import androidx.core.content.edit

class AndroidBridge(
    private val context: Context,
    private val onServerConfigured: (String) -> Unit,
    private val onRetry: () -> Unit,
) {
    /**
     * Asks the app to use this server. An empty address means the default server.
     * Returns false when the address is rejected (unknown scheme or no host).
     * Saving and navigating happen in MainActivity on the UI thread, which checks
     * the calling page first (see ServerAddress.bridgeAction): only the bundled
     * setup page may navigate, remote pages may only re-save their own origin.
     */
    @JavascriptInterface
    fun setServerUrl(url: String): Boolean {
        val normalized = ServerAddress.normalizeOrDefault(url) ?: return false
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

    /** Retry the page that last failed to load (used by the error screen). */
    @JavascriptInterface
    fun retry() {
        onRetry()
    }

    @JavascriptInterface
    fun getDefaultServerUrl(): String = ServerAddress.DEFAULT

    companion object {
        fun normalizeBaseUrl(raw: String): String? = ServerAddress.normalize(raw)
    }
}
