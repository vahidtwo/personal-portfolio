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
import android.os.SystemClock
import android.util.Log
import android.view.View
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.edit
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.WindowCompat
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private lateinit var loading: View

    /** The page that last failed to load; «تلاش دوباره» reloads it. */
    private var lastFailedUrl: String? = null
    /** Set while the failed page is being replaced by the error screen. */
    private var errorPending = false
    /** After a successful retry, drop the error screen from the back stack. */
    private var clearHistoryOnSuccess = false

    /** v11: the launch splash stays until the first page paints (or [StartupGate.SPLASH_MAX_MS]). */
    private val startup = StartupGate()
    /** v11: main-frame errors for a page the service worker actually served are ignored (see MainFrameErrors). */
    private val frameErrors = MainFrameErrors()

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        startup.created(SystemClock.uptimeMillis())
        // A tab opened from the native home shows the skeleton cover at once instead of holding the window
        // blank behind the splash condition; the cover still hides at the first paint.
        val tabLaunch = intent?.getStringExtra(EXTRA_PATH) != null
        installSplashScreen().setKeepOnScreenCondition { !tabLaunch && startup.keepSplash(SystemClock.uptimeMillis()) }
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, true)
        window.statusBarColor = Color.parseColor("#050608")
        window.navigationBarColor = Color.parseColor("#050608")
        setContentView(R.layout.activity_main)
        web = findViewById(R.id.web)
        loading = findViewById(R.id.loading)
        val bgColor = if (isNight()) Color.parseColor("#050608") else Color.parseColor("#EEF1F8")
        web.setBackgroundColor(bgColor)
        if (tabLaunch) {
            window.statusBarColor = bgColor
            // Same colour as the native bar composited over the page, so the inset does not jump on a tab switch.
            window.navigationBarColor = WebNav.systemBarColor(isNight())
            if (android.os.Build.VERSION.SDK_INT >= 28) window.navigationBarDividerColor = Color.TRANSPARENT
            WindowCompat.getInsetsController(window, window.decorView).apply {
                isAppearanceLightStatusBars = !isNight(); isAppearanceLightNavigationBars = !isNight()
            }
            findViewById<View>(android.R.id.content).setBackgroundColor(bgColor)
            LoadingSkeleton.install(loading as android.widget.FrameLayout, isNight())
            showLoading(true)
        }

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
                if (handOffToNative(target)) return true
                if (ServerAddress.opensExternally(target.scheme, target.host)) {
                    runCatching { startActivity(Intent(Intent.ACTION_VIEW, target).addCategory(Intent.CATEGORY_BROWSABLE)) }
                    return true
                }
                if (isAllowedRemoteUrl(target)) return false
                return true
            }

            override fun onPageCommitVisible(view: WebView, url: String?) {
                super.onPageCommitVisible(view, url)
                // v11: first paint of the new page -> drop the splash/cover now, not at onPageFinished (load).
                // Not while the hidden old-host /health page is read, and not for a failed page (error screen next).
                frameErrors.committed(url)
                if (StartupGate.revealOnCommit(url, readingOldPrivacy, errorPending || frameErrors.pending != null)) {
                    showLoading(false)
                    startup.firstPaint(SystemClock.uptimeMillis(), url)
                }
                // Earliest point after the /auth -> /dashboard redirect: persist the new session cookie before the
                // page finishes loading, so a force-stop ~1 s after login keeps the user signed in.
                CookieManager.getInstance().flush()
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                if (url != null && handOffToNative(Uri.parse(url))) { view.stopLoading(); return }
                frameErrors.started(url)
                if (url != null && url.startsWith("https://")) showLoading(true)
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                super.onReceivedError(view, request, error)
                if (!request.isForMainFrame) return
                val failed = request.url?.toString()
                if (frameErrors.holdNetworkError(failed, readingOldPrivacy)) {
                    Log.i(StartupGate.TAG, "main-frame error held (${error.errorCode})")
                    view.postDelayed({ decideHeldError(null) }, MainFrameErrors.DECIDE_AFTER_MS)
                } else {
                    showConnectionError(failed)
                }
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
                    val failed = request.url?.toString()
                    if (frameErrors.holdHttpError(failed, readingOldPrivacy)) {
                        view.postDelayed({ decideHeldError(null) }, MainFrameErrors.DECIDE_AFTER_MS)
                    } else {
                        showConnectionError(failed)
                    }
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
                // Persist the session cookie right after each page (e.g. the /auth -> /dashboard login), not only
                // in onPause: a process kill without onPause (force-stop, OOM) otherwise logs the user out.
                CookieManager.getInstance().flush()
                if (frameErrors.isPendingFor(url)) {
                    decideHeldError { finishPage(view, url) }
                    return
                }
                finishPage(view, url)
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

        SmsPrefs.ensureMigrated(this)
        askNotificationPermission()
        val tabPath = intent?.getStringExtra(EXTRA_PATH)
        if (tabPath != null && savedInstanceState == null) {
            loadRemote(NativeSession.BASE, tabPath)
        } else {
            startWithHostMove(savedInstanceState)
        }
    }

    /** True while the hidden WebView reads the old origin's privacy flag before the move. */
    private var readingOldPrivacy = false

    /**
     * v9 move: a saved old default host becomes https://daraiito.ir after a quick /health check.
     * Probe fails -> keep the old host, try again next launch. Custom hosts and fresh installs
     * skip this. At most one try per cold launch. Old-host cookies are kept (rollback + SMS).
     * Hidden amounts stay hidden: the old origin's "privacy-portfolio" flag is read first and
     * carried over with the #36 #hide=1 handoff (plus a direct write on the new origin).
     */
    private fun startWithHostMove(savedInstanceState: Bundle?) {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        val raw = prefs.getString(KEY_URL, "")
        if (!ServerAddress.shouldMigrate(
                raw, prefs.getBoolean(KEY_HOST_MIGRATED, false),
                prefs.getInt(KEY_HOST_FALLBACK_COUNT, 0), moveTriedThisLaunch,
            )
        ) {
            if (ServerAddress.shouldProbeOnLaunch(
                    savedBaseUrl(), prefs.getBoolean(KEY_HOST_MIGRATED, false),
                    prefs.getBoolean(KEY_HOST_CONFIRMED, false), launchProbeDone,
                )
            ) {
                probeNewHostThenStart(savedInstanceState)
            } else {
                restoreOrSetup(savedInstanceState)
            }
            return
        }
        moveTriedThisLaunch = true
        showLoading(true)
        thread {
            val ok = HealthProbe.isUp(ServerAddress.DEFAULT)
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                if (ok) readOldPrivacyThenMove() else restoreOrSetup(savedInstanceState)
            }
        }
    }

    /** Opens the old origin's /health (tiny JSON page) only to read its localStorage flag. */
    private fun readOldPrivacyThenMove() {
        readingOldPrivacy = true
        showLoading(true)
        web.loadUrl("${ServerAddress.OLD_DEFAULT}/health")
        // Can't read it in time -> hide (fail-safe: never reveal).
        web.postDelayed({ finishMove(null) }, PRIVACY_READ_TIMEOUT_MS)
    }

    private fun finishMove(jsResult: String?) {
        if (!readingOldPrivacy) return
        readingOldPrivacy = false
        if (isFinishing || isDestroyed) return
        val hide = ServerAddress.hideAfterMove(jsResult)
        getSharedPreferences(PREFS, MODE_PRIVATE).edit {
            putString(KEY_URL, ServerAddress.DEFAULT)
            putBoolean(KEY_HOST_MIGRATED, true)
            putBoolean(KEY_PENDING_HIDE, hide)
        }
        web.stopLoading()
        web.clearHistory()
        showLoading(true)
        web.loadUrl(ServerAddress.moveTarget(hide))
    }

    /** Belt and braces for the handoff: write the flag on the new origin itself, then reload once. */
    private fun applyPendingHide(url: String) {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        if (!prefs.getBoolean(KEY_PENDING_HIDE, false)) return
        if (runCatching { Uri.parse(url).host }.getOrNull() != "daraiito.ir") return
        prefs.edit { putBoolean(KEY_PENDING_HIDE, false) }
        web.evaluateJavascript(
            "(function(){try{if(localStorage.getItem('privacy-portfolio')==='1')return 'same';" +
                "localStorage.setItem('privacy-portfolio','1');return 'set'}catch(e){return 'err'}})()",
        ) { r -> if (r == "\"set\"") web.reload() }
    }

    /** Native /health check before loading the unconfirmed new host; dead -> old host (if its /health is OK). */
    private fun probeNewHostThenStart(savedInstanceState: Bundle?) {
        launchProbeDone = true
        showLoading(true)
        thread {
            val newOk = HealthProbe.isUp(ServerAddress.DEFAULT)
            val fallBack = !newOk && fallbackAllowed("${ServerAddress.DEFAULT}/health") &&
                HealthProbe.isUp(ServerAddress.OLD_DEFAULT)
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                if (newOk) newHostOkThisLaunch = true
                if (fallBack) doFallBack() else restoreOrSetup(savedInstanceState)
            }
        }
    }

    private fun fallbackAllowed(failedUrl: String?): Boolean {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        return ServerAddress.shouldFallBack(
            savedBaseUrl(), prefs.getBoolean(KEY_HOST_MIGRATED, false), fallbackThisLaunch, failedUrl,
        )
    }

    /** After the move, a failing new host sends the user back to the old one (once per launch). */
    private fun maybeFallBackToOldHost(failedUrl: String?) {
        if (!fallbackAllowed(failedUrl)) return
        fallbackThisLaunch = true
        thread {
            if (!HealthProbe.isUp(ServerAddress.OLD_DEFAULT)) return@thread
            runOnUiThread { if (!isFinishing && !isDestroyed) doFallBack() }
        }
    }

    /** host_migrated=false -> the move is tried again on a later cold launch (count caps it at 3). */
    private fun doFallBack() {
        fallbackThisLaunch = true
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        prefs.edit {
            putBoolean(KEY_HOST_MIGRATED, false)
            putBoolean(KEY_HOST_FALLBACK, true)
            putInt(KEY_HOST_FALLBACK_COUNT, prefs.getInt(KEY_HOST_FALLBACK_COUNT, 0) + 1)
        }
        lastFailedUrl = null
        errorPending = false
        loadRemote(ServerAddress.OLD_DEFAULT, "/dashboard")
    }

    /** SW-served offline page = a failed load; a real new-host page after an OK probe confirms the host. */
    private fun checkNewHostPage(url: String) {
        if (runCatching { Uri.parse(url).host }.getOrNull() != "daraiito.ir") return
        web.evaluateJavascript(ServerAddress.OFFLINE_MARKER_JS) { r ->
            if (ServerAddress.isOfflinePage(r)) {
                maybeFallBackToOldHost(url)
            } else if (newHostOkThisLaunch) {
                getSharedPreferences(PREFS, MODE_PRIVATE).edit { putBoolean(KEY_HOST_CONFIRMED, true) }
            }
        }
    }

    /** An SMS could not be saved because nobody is signed in: say so in the app too. */
    private fun showSmsLoginPromptIfNeeded() {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        if (!prefs.getBoolean(SmsReceiver.KEY_LOGIN_NEEDED, false)) return
        prefs.edit { putBoolean(SmsReceiver.KEY_LOGIN_NEEDED, false) }
        Toast.makeText(this, "پیامک خرج رسید ولی وارد نشده‌اید؛ بعد از ورود خودکار ذخیره می‌شود.", Toast.LENGTH_LONG).show()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
    }

    /** Launcher shortcut «تنظیمات اتصال»: open setup with the address box already open. */
    private fun openAdvancedSetup() {
        UpdateNotifier.hideQuietly()
        errorPending = false
        showLoading(false)
        web.stopLoading()
        web.loadUrl(SETUP_ADVANCED_ASSET)
    }

    override fun onResume() {
        super.onResume()
        showSmsLoginPromptIfNeeded()
        SmsReceiver.flushQueued(this)
        UpdateNotifier.onResume(this)
    }

    override fun onDestroy() {
        UpdateNotifier.hideQuietly()
        super.onDestroy()
    }

    /** The update sheet may only cover a fully loaded, logged-in site page. */
    fun canShowUpdateSheet(): Boolean =
        !isFinishing && !isDestroyed && loading.visibility != View.VISIBLE && !errorPending &&
            UpdateCheck.isEligiblePage(web.url, savedBaseUrl())

    /** Keeps TalkBack inside the update sheet while it is open. */
    fun setPageHiddenFromAccessibility(hidden: Boolean) {
        web.importantForAccessibility = if (hidden) {
            View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
        } else {
            View.IMPORTANT_FOR_ACCESSIBILITY_AUTO
        }
    }

    override fun onPause() {
        super.onPause()
        // Persist the login cookie so reopening the app keeps the session.
        CookieManager.getInstance().flush()
    }

    override fun onStop() {
        super.onStop()
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

    private fun isNight(): Boolean =
        (resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK) ==
            android.content.res.Configuration.UI_MODE_NIGHT_YES

    private fun showLoading(show: Boolean) {
        loading.visibility = if (show) View.VISIBLE else View.GONE
    }

    /** Never leave Android's "Webpage not available" page up: show our Persian error screen. */
    private fun finishPage(view: WebView, url: String) {
        if (readingOldPrivacy) {
            if (url.startsWith(ServerAddress.OLD_DEFAULT)) {
                view.evaluateJavascript(
                    "(function(){try{return localStorage.getItem('privacy-portfolio')}catch(e){return 'err'}})()",
                ) { r -> finishMove(r) }
            }
            return
        }
        if (url.startsWith("https://")) {
            applyPendingHide(url)
            checkNewHostPage(url)
        }
        if (url.startsWith("file:")) {
            errorPending = false
            showLoading(false)
            startup.firstPaint(SystemClock.uptimeMillis(), url)
            UpdateNotifier.hideQuietly()
            return
        }
        if (errorPending) return // the error screen is on its way
        showLoading(false)
        startup.firstPaint(SystemClock.uptimeMillis(), url)
        Log.i(StartupGate.TAG, "pageFinished +${SystemClock.uptimeMillis() - startup.createdAt}ms")
        if (url.startsWith("https://")) {
            if (clearHistoryOnSuccess) {
                clearHistoryOnSuccess = false
                view.clearHistory()
            }
            PushRegistrar.registerFcmToken(this@MainActivity)
        }
        UpdateNotifier.onPageLoaded(this@MainActivity, url, savedBaseUrl())
    }

    /** Decide a held main-frame error: served page = ignore and [onServed]; else the error screen. */
    private fun decideHeldError(onServed: (() -> Unit)?) {
        val url = frameErrors.pending ?: return
        web.evaluateJavascript(MainFrameErrors.SERVED_JS) { r ->
            if (!frameErrors.isPendingFor(url)) return@evaluateJavascript
            if (frameErrors.resolve(r)) {
                Log.i(StartupGate.TAG, "main-frame error ignored: page was served")
                if (onServed != null) onServed() else if (!errorPending) { showLoading(false); startup.firstPaint(SystemClock.uptimeMillis(), url) }
            } else {
                showConnectionError(url)
            }
        }
    }

    private fun showConnectionError(failedUrl: String?) {
        if (readingOldPrivacy) { finishMove(null); return } // old host unreachable: move anyway, hidden
        UpdateNotifier.hideQuietly()
        if (failedUrl != null && failedUrl.startsWith("https://")) lastFailedUrl = failedUrl
        errorPending = true
        showLoading(true)
        // The saved address is kept on purpose: being offline never wipes it.
        web.stopLoading()
        web.loadUrl(ERROR_ASSET + "?theme=" + (if (isNight()) "dark" else "light"))
        maybeFallBackToOldHost(failedUrl)
    }

    private fun retryLast() {
        clearHistoryOnSuccess = true
        web.loadUrl(retryTarget(lastFailedUrl, NativeSession.BASE))
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
                loadRemote(NativeSession.BASE, "/dashboard")
            }
            return
        }
        loadRemote(saved ?: NativeSession.BASE, "/dashboard")
    }

    /**
     * Phase 4: home and login are native. A WebView tab that navigates to the plain home (/dashboard) or to the
     * sign-in page (after a web logout or an expired session) closes and hands back to [HomeActivity].
     */
    private fun handOffToNative(uri: Uri): Boolean {
        if (uri.host != Uri.parse(NativeSession.BASE).host) return false
        val path = uri.path.orEmpty().trimEnd('/')
        val toAuth = path == "/auth" || path == "/login"
        val toHome = path == "/dashboard" && uri.getQueryParameter("tab") == null
        if (!toAuth && !toHome) return false
        if (isFinishing) return true
        if (toAuth) {
            startActivity(Intent(this, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        finish()
        return true
    }

    fun loadRemote(base: String, path: String) {
        val normalized = AndroidBridge.normalizeBaseUrl(base) ?: return
        saveBaseUrl(normalized)
        val suffix = if (path.startsWith("/")) path else "/$path"
        showLoading(true)
        Log.i(StartupGate.TAG, "loadUrl +${SystemClock.uptimeMillis() - startup.createdAt}ms")
        startup.handOffToCover()
        web.loadUrl("$normalized$suffix")
    }

    fun savedBaseUrl(): String? {
        val raw = getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_URL, "") ?: ""
        return AndroidBridge.normalizeBaseUrl(raw)
    }

    private fun saveBaseUrl(url: String) {
        getSharedPreferences(PREFS, MODE_PRIVATE).edit {
            putString(KEY_URL, url)
        }
    }

    private fun isAllowedRemoteUrl(uri: Uri): Boolean =
        ServerAddress.isAllowedRemote(uri.scheme, uri.host, savedBaseUrl())

    /** SMS permission is asked only from SMS settings, when the user turns the switch on. */
    private fun askNotificationPermission() {
        val needed = mutableListOf<String>()
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
        const val KEY_HOST_MIGRATED = "host_migrated"
        const val KEY_HOST_FALLBACK = "host_fallback_done"
        const val KEY_HOST_FALLBACK_COUNT = "host_fallback_count"
        const val KEY_PENDING_HIDE = "host_move_pending_hide"
        const val KEY_HOST_CONFIRMED = "host_confirmed"
        @Volatile private var launchProbeDone = false
        @Volatile private var newHostOkThisLaunch = false
        private const val PRIVACY_READ_TIMEOUT_MS = 6000L
        /** Process-wide: reset on every cold launch. */
        @Volatile private var moveTriedThisLaunch = false
        @Volatile private var fallbackThisLaunch = false
        const val KEY_PHRASE = "sms_phrase"
        const val DEFAULT_PHRASE = "برداشت"
        private const val SETUP_ASSET = "file:///android_asset/www/setup.html"
        /** Phase 4: retry-only error page (no setup link). */
        private const val ERROR_ASSET = "file:///android_asset/www/error.html"
        private const val SETUP_ADVANCED_ASSET = "$SETUP_ASSET?advanced=1"
        private const val STATE_FAILED_URL = "last_failed_url"
        const val ACTION_OPEN_SETUP = "app.myinventory.OPEN_SETUP"
        const val EXTRA_PATH = "app.myinventory.PATH"

        /** «تلاش دوباره» reloads the failed page only when it is on the app's own origin; else the home. */
        fun retryTarget(failed: String?, base: String): String {
            val host = runCatching { java.net.URI(base).host }.getOrNull()
            val ok = failed != null && runCatching { java.net.URI(failed) }.getOrNull()?.let {
                it.scheme == java.net.URI(base).scheme && it.host == host
            } == true
            return if (ok) failed!! else "$base/dashboard"
        }
    }
}
