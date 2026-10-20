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

    /** v5 pages only: keywords now live in the app's own SMS settings screen. Ignored. */
    @JavascriptInterface
    fun setSmsPhrase(@Suppress("UNUSED_PARAMETER") phrase: String) {}

    /** Keywords never leave the phone, so web pages don't get them. */
    @JavascriptInterface
    fun getSmsPhrase(): String = ""

    /** Opens the native SMS settings screen (keywords, switch, permission). */
    @JavascriptInterface
    fun openSmsSettings() {
        context.startActivity(
            android.content.Intent(context, SmsSettingsActivity::class.java)
                .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        )
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
