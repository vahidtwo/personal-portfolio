package app.myinventory

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.core.content.FileProvider
import androidx.core.content.edit
import androidx.core.content.pm.PackageInfoCompat
import java.io.File
import java.lang.ref.WeakReference
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * In-app update notice (approved design, spec §10).
 * - One check per app launch, only after the first eligible page (logged-in site page) has
 *   loaded; background thread, 5 s timeouts; offline / errors / bad JSON = nothing shown.
 * - Never over setup, «در حال اتصال…», error or advanced screens, or before login.
 * - «بعداً», Back, scrim tap and swipe-down snooze it for 24 h (wall clock, persisted) or
 *   until a higher versionCode appears.
 * - Download -> SHA-256 + signing-cert check -> installer (unknown-sources step on first use).
 * - min_required is parsed but ignored: forced updates are not approved.
 */
object UpdateNotifier {
    private const val KEY_DISMISSED_CODE = "update_dismissed_version_code"
    private const val KEY_DISMISSED_AT = "update_dismissed_at_ms"
    private const val TIMEOUT_MS = 5000
    private const val MAX_BYTES = 64 * 1024

    private enum class State { IDLE, AVAILABLE, DOWNLOADING, READY, FAILED, DISMISSED }

    private val main = Handler(Looper.getMainLooper())
    @Volatile private var checkStarted = false
    private var state = State.IDLE
    private var info: UpdateCheck.Info? = null
    private var downloadUrl: String? = null
    private var readyFile: File? = null
    private var downloader: UpdateDownloader? = null
    private var progressDone = 0L
    private var progressTotal = 0L
    private var sheet: UpdateSheet? = null
    private var activityRef = WeakReference<MainActivity>(null)

    /** Injectable wall clock (QA can also just move the device clock). */
    var clock: () -> Long = { System.currentTimeMillis() }

    private val httpAllowedHost: String? get() = BuildConfig.UPDATE_HTTP_HOST.ifEmpty { null }
    private fun checkBase(savedBase: String?): String? = BuildConfig.UPDATE_BASE_URL.ifEmpty { savedBase }

    /** From MainActivity.onPageFinished for every successfully loaded page. */
    fun onPageLoaded(activity: MainActivity, pageUrl: String?, savedBase: String?) {
        if (!UpdateCheck.inAppUpdatesEnabled) return
        activityRef = WeakReference(activity)
        if (!UpdateCheck.isEligiblePage(pageUrl, savedBase)) {
            hideQuietly()
            return
        }
        if (!checkStarted) startCheck(activity, savedBase) else maybeShow()
    }

    fun onResume(activity: MainActivity) {
        if (!UpdateCheck.inAppUpdatesEnabled) return
        activityRef = WeakReference(activity)
        maybeShow()
        refresh() // e.g. back from the «نصب از منابع ناشناس» settings screen
    }

    /** Setup / error / advanced screen about to show, or the activity is going away. */
    fun hideQuietly() {
        sheet?.dismissQuietly()
        sheet = null
    }

    private fun startCheck(activity: MainActivity, savedBase: String?) {
        if (!UpdateCheck.inAppUpdatesEnabled) return
        checkStarted = true
        val base = checkBase(savedBase) ?: return
        val endpoint = UpdateCheck.resolveDownloadUrl(base, "/api/app-version", httpAllowedHost) ?: return
        val appContext = activity.applicationContext
        thread(name = "update-check", isDaemon = true) {
            try {
                val parsed = UpdateCheck.parse(fetch(endpoint)) ?: return@thread
                val url = UpdateCheck.resolveDownloadUrl(base, parsed.url, httpAllowedHost) ?: return@thread
                val installed = installedCode(appContext)
                val prefs = prefs(appContext)
                val notify = UpdateCheck.shouldNotify(
                    remoteCode = parsed.versionCode,
                    installedCode = installed,
                    dismissedCode = prefs.getLong(KEY_DISMISSED_CODE, 0L),
                    dismissedAtMs = prefs.getLong(KEY_DISMISSED_AT, 0L),
                    nowMs = clock(),
                )
                if (!notify) return@thread
                main.post {
                    info = parsed
                    downloadUrl = url
                    state = State.AVAILABLE
                    maybeShow()
                }
            } catch (_: Throwable) {
                // offline, timeout, 5xx, bad JSON: show nothing
            }
        }
    }

    private fun fetch(url: String): String? {
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = TIMEOUT_MS
            conn.readTimeout = TIMEOUT_MS
            conn.instanceFollowRedirects = false
            conn.useCaches = false
            conn.setRequestProperty("Accept", "application/json")
            if (conn.responseCode != 200) return null
            val out = java.io.ByteArrayOutputStream()
            conn.inputStream.use { input ->
                val chunk = ByteArray(8192)
                while (true) {
                    val n = input.read(chunk)
                    if (n < 0) break
                    out.write(chunk, 0, n)
                    if (out.size() > MAX_BYTES) return null
                }
            }
            return String(out.toByteArray(), Charsets.UTF_8)
        } finally {
            conn.disconnect()
        }
    }

    private fun maybeShow() {
        val activity = activityRef.get() ?: return
        val current = info ?: return
        if (state !in setOf(State.AVAILABLE, State.DOWNLOADING, State.READY, State.FAILED)) return
        if (!activity.canShowUpdateSheet()) return
        if (sheet?.isShowing == true) return
        sheet = UpdateSheet(activity, onPrimary = ::onPrimary, onDismissByUser = ::onDismissByUser)
        render(activity, current)
        sheet?.show()
        if (state == State.DOWNLOADING) sheet?.setProgress(progressDone, progressTotal)
    }

    private fun refresh() {
        val activity = activityRef.get() ?: return
        val current = info ?: return
        if (sheet?.isShowing == true) render(activity, current)
    }

    private fun render(activity: MainActivity, current: UpdateCheck.Info) {
        val mode = when (state) {
            State.DOWNLOADING -> UpdateSheet.Mode.DOWNLOADING
            State.READY -> UpdateSheet.Mode.READY
            State.FAILED -> UpdateSheet.Mode.FAILED
            else -> UpdateSheet.Mode.AVAILABLE
        }
        sheet?.render(mode, current, installedCode(activity), needsInstallPermission(activity))
    }

    private fun onPrimary() {
        when (state) {
            State.AVAILABLE, State.FAILED -> startDownload()
            State.READY -> install()
            else -> Unit
        }
    }

    /** «بعداً» / Back / scrim / swipe-down. In the downloading state this is «لغو». */
    private fun onDismissByUser() {
        val activity = activityRef.get()
        val current = info
        if (state == State.DOWNLOADING) {
            downloader?.cancel()
            downloader = null
        }
        if (activity != null && current != null) {
            prefs(activity).edit {
                putLong(KEY_DISMISSED_CODE, current.versionCode)
                putLong(KEY_DISMISSED_AT, clock())
            }
        }
        state = State.DISMISSED
        sheet = null
    }

    private fun startDownload() {
        val activity = activityRef.get() ?: return
        val current = info ?: return
        val url = downloadUrl ?: return
        state = State.DOWNLOADING
        progressDone = 0
        progressTotal = current.sizeBytes ?: 0
        render(activity, current)
        val d = UpdateDownloader(activity, current, url, object : UpdateDownloader.Listener {
            override fun onProgress(done: Long, total: Long) {
                progressDone = done
                progressTotal = total
                sheet?.setProgress(done, total)
            }

            override fun onReady(file: File) {
                readyFile = file
                state = State.READY
                downloader = null
                refreshOrShow()
            }

            override fun onFailed() {
                state = State.FAILED
                downloader = null
                refreshOrShow()
            }
        })
        downloader = d
        d.start()
    }

    private fun refreshOrShow() {
        if (sheet?.isShowing == true) refresh() else maybeShow()
    }

    private fun install() {
        val activity = activityRef.get() ?: return
        val file = readyFile?.takeIf { it.isFile } ?: run {
            state = State.FAILED
            refresh()
            return
        }
        if (needsInstallPermission(activity)) {
            // First use: Android's per-app «نصب از منابع ناشناس» switch. On return, onResume
            // re-renders the ready screen (callout hidden once allowed).
            try {
                activity.startActivity(
                    Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}")),
                )
            } catch (_: ActivityNotFoundException) {
            }
            return
        }
        try {
            val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", file)
            activity.startActivity(
                Intent(Intent.ACTION_VIEW)
                    .setDataAndType(uri, "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION),
            )
        } catch (_: Throwable) {
            state = State.FAILED
            refresh()
        }
    }

    private fun needsInstallPermission(context: Context): Boolean =
        Build.VERSION.SDK_INT >= 26 && !context.packageManager.canRequestPackageInstalls()

    private fun installedCode(context: Context): Long =
        PackageInfoCompat.getLongVersionCode(context.packageManager.getPackageInfo(context.packageName, 0))

    private fun prefs(context: Context) =
        context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
}
