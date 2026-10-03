package app.myinventory

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.edit
import androidx.core.view.WindowCompat

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        window.statusBarColor = Color.parseColor("#050608")
        window.navigationBarColor = Color.parseColor("#050608")
        setContentView(R.layout.activity_main)
        web = findViewById(R.id.web)

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
            AndroidBridge(this) { base -> loadRemote(base, "/dashboard") },
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

            override fun onPageFinished(view: WebView, url: String?) {
                super.onPageFinished(view, url)
                url ?: return
                if (url.startsWith("https://")) {
                    AndroidBridge.normalizeBaseUrl(url)?.let { origin ->
                        saveBaseUrl(origin)
                    }
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
        restoreOrSetup(savedInstanceState)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    private fun restoreOrSetup(savedInstanceState: Bundle?) {
        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState)
            return
        }
        val saved = savedBaseUrl()
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
    }
}
