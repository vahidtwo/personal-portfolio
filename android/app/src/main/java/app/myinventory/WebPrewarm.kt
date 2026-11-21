package app.myinventory

import android.annotation.SuppressLint
import android.content.Context
import android.os.Looper
import android.webkit.WebView

/**
 * After the native home is on screen, load a tiny same-origin page in a hidden WebView so the WebView
 * provider, renderer and the site's service worker are already up when a WebView tab opens.
 */
object WebPrewarm {
    private var view: WebView? = null

    @SuppressLint("SetJavaScriptEnabled")
    fun start(context: Context) {
        if (view != null) return
        Looper.myQueue().addIdleHandler {
            if (view == null) {
                runCatching {
                    view = WebView(context.applicationContext).apply {
                        settings.javaScriptEnabled = true
                        settings.domStorageEnabled = true
                        loadUrl(NativeSession.BASE + "/offline.html")
                    }
                }
            }
            false
        }
    }

    fun stop() {
        view?.let { it.stopLoading(); it.clearCache(true); it.destroy() }
        view = null
    }
}
