package app.myinventory

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.net.http.SslError
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.edit
import androidx.core.view.WindowCompat

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private lateinit var loading: View

    /** The page that last failed to load; «تلاش دوباره» reloads it. */
    private var lastFailedUrl: String? = null
    /** Set while the failed page is being replaced by the error screen. */
    private var errorPending = false
    /** After a successful retry, drop the error screen from the back stack. */
    private var clearHistoryOnSuccess = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        window.statusBarColor = Color.parseColor("#050608")
        window.navigationBarColor = Color.parseColor("#050608")
        setContentView(R.layout.activity_main)
        web = findViewById(R.id.web)
        loading = findViewById(R.id.loading)
        web.setBackgroundColor(Color.parseColor("#050608"))

        val cookieManager = CookieManager.getInstance()
        cookieManager.setAcceptCookie(true)
        cookieManager.setAcceptThirdPartyCookies(web, true)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = false
            loadWithOverviewMode = true
            useWideViewPort = true
            builtInZoomControls = false
            displayZoomControls = false
            mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                safeBrowsingEnabled = true
            }
        }

        web.addJavascriptInterface(
            // @JavascriptInterface methods run on the "JavaBridge" thread, but
            // WebView.loadUrl must be called on the UI thread, or it throws and
            // the setup button silently does nothing.
            AndroidBridge(
                this,
                onServerConfigured = { base -> runOnUiThread { onBridgeServerUrl(base) } },
                onRetry = { runOnUiThread { retryLast() } },
            ),
            "AndroidBridge",
        )

        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (!request.isForMainFrame) return false
                val target = request.url ?: return false
                if (target.scheme == "file") return false
                if (isAllowedRemoteUrl(target)) return false
                return true
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                if (url != null && url.startsWith("https://")) showLoading(true)
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                super.onReceivedError(view, request, error)
                if (request.isForMainFrame) showConnectionError(request.url?.toString())
            }

            override fun onReceivedHttpError(
                view: WebView,
                request: WebResourceRequest,
                errorResponse: WebResourceResponse,
            ) {
                super.onReceivedHttpError(view, request, errorResponse)
                if (!request.isForMainFrame) return
                val status = errorResponse.statusCode
                val path = request.url?.path.orEmpty().trimEnd('/')
                // 5xx = server down / deploying; 404 on /dashboard = not our server.
                if (status >= 500 || (status == 404 && path == "/dashboard")) {
                    showConnectionError(request.url?.toString())
                }
            }

            @SuppressLint("WebViewClientOnReceivedSslError")
            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                handler.cancel()
                showConnectionError(error.url)
            }

            override fun onPageFinished(view: WebView, url: String?) {
                super.onPageFinished(view, url)
                url ?: return
                if (url.startsWith("file:")) {
                    errorPending = false
                    showLoading(false)
                    return
                }
                if (errorPending) return // the error screen is on its way
                showLoading(false)
                if (url.startsWith("https://")) {
                    if (clearHistoryOnSuccess) {
                        clearHistoryOnSuccess = false
                        view.clearHistory()
                    }
                    PushRegistrar.registerFcmToken(this@MainActivity)
                }
            }
        }

        onBackPressedDispatcher.addCallback(this) {
            if (web.canGoBack()) {
                web.goBack()
            } else {
                isEnabled = false
                onBackPressedDispatcher.onBackPressed()
            }
        }

        askSmsPermission()
        UpdateNotifier.checkOnce(this, savedBaseUrl())
        if (intent?.action == ACTION_OPEN_SETUP) {
            openAdvancedSetup()
        } else {
            restoreOrSetup(savedInstanceState)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.action == ACTION_OPEN_SETUP) openAdvancedSetup()
    }

    /** Launcher shortcut «تنظیمات اتصال»: open setup with the address box already open. */
    private fun openAdvancedSetup() {
        errorPending = false
        showLoading(false)
        web.stopLoading()
        web.loadUrl(SETUP_ADVANCED_ASSET)
    }

    override fun onPause() {
        super.onPause()
        // Persist the login cookie so reopening the app keeps the session.
        CookieManager.getInstance().flush()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
        outState.putString(STATE_FAILED_URL, lastFailedUrl)
    }

    /** Runs on the UI thread so web.url is the page that called setServerUrl. */
    private fun onBridgeServerUrl(base: String) {
        when (ServerAddress.bridgeAction(web.url, base)) {
            ServerAddress.BridgeAction.NAVIGATE -> loadRemote(base, "/dashboard")
            ServerAddress.BridgeAction.SAVE_ONLY -> saveBaseUrl(base)
            ServerAddress.BridgeAction.IGNORE -> Unit
        }
    }

    private fun showLoading(show: Boolean) {
        loading.visibility = if (show) View.VISIBLE else View.GONE
    }

    /** Never leave Android's "Webpage not available" page up: show our Persian error screen. */
    private fun showConnectionError(failedUrl: String?) {
        if (failedUrl != null && failedUrl.startsWith("https://")) lastFailedUrl = failedUrl
        errorPending = true
        showLoading(true)
        // The saved address is kept on purpose: being offline never wipes it.
        web.stopLoading()
        web.loadUrl(SETUP_ERROR_ASSET)
    }

    private fun retryLast() {
        val target = lastFailedUrl
            ?: savedBaseUrl()?.let { "$it/dashboard" }
        if (target == null) {
            web.loadUrl(SETUP_ASSET)
            return
        }
        clearHistoryOnSuccess = true
        web.loadUrl(target)
    }

    private fun restoreOrSetup(savedInstanceState: Bundle?) {
        val saved = savedBaseUrl()
        if (savedInstanceState != null) {
            lastFailedUrl = savedInstanceState.getString(STATE_FAILED_URL)
            web.restoreState(savedInstanceState)
            // If the activity was recreated on the setup page after an address was
            // already saved, go to the dashboard instead of showing setup again.
            val restoredUrl = web.url
            if (saved != null && (restoredUrl == null || restoredUrl.startsWith(SETUP_ASSET))) {
                loadRemote(saved, "/dashboard")
            } else if (restoredUrl == null) {
                web.loadUrl(SETUP_ASSET)
            }
            return
        }
        if (saved != null) {
            loadRemote(saved, "/dashboard")
        } else {
            web.loadUrl(SETUP_ASSET)
        }
    }

    fun loadRemote(base: String, path: String) {
        val normalized = AndroidBridge.normalizeBaseUrl(base) ?: return
        saveBaseUrl(normalized)
        val suffix = if (path.startsWith("/")) path else "/$path"
        showLoading(true)
        web.loadUrl("$normalized$suffix")
    }

    private fun savedBaseUrl(): String? {
        val raw = getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_URL, "") ?: ""
        return AndroidBridge.normalizeBaseUrl(raw)
    }

    private fun saveBaseUrl(url: String) {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit {
            putString(KEY_URL, url)
        }
    }

    private fun isAllowedRemoteUrl(uri: Uri): Boolean {
        if (uri.scheme != "https") return false
        val base = savedBaseUrl() ?: return true
        val baseHost = runCatching { Uri.parse(base).host }.getOrNull() ?: return false
        return uri.host == baseHost
    }

    private fun askSmsPermission() {
        val needed = mutableListOf(Manifest.permission.RECEIVE_SMS)
        if (Build.VERSION.SDK_INT >= 33) {
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = needed.filter {
            ActivityCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 1)
        }
    }

    companion object {
        const val PREFS = "app.myinventory"
        const val KEY_URL = "base_url"
        const val KEY_PHRASE = "sms_phrase"
        const val DEFAULT_PHRASE = "برداشت"
        private const val SETUP_ASSET = "file:///android_asset/www/setup.html"
        private const val SETUP_ERROR_ASSET = "$SETUP_ASSET?error=connect"
        private const val SETUP_ADVANCED_ASSET = "$SETUP_ASSET?advanced=1"
        private const val STATE_FAILED_URL = "last_failed_url"
        const val ACTION_OPEN_SETUP = "app.myinventory.OPEN_SETUP"
    }
}
