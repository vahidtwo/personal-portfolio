package app.myinventory

import android.util.Log

/**
 * v11 startup: the native launch splash (core-splashscreen) is held until the WebView's first paint
 * (onPageCommitVisible of the real page, or the local setup/error page), but never longer than [SPLASH_MAX_MS];
 * after that the logo cover in activity_main.xml keeps hiding a page that is still loading.
 * Pure logic (no Android types besides Log) so it is unit-tested.
 */
class StartupGate {
    var createdAt = 0L
        private set
    private var painted = false
    private var handedOff = false

    fun created(now: Long) {
        createdAt = now
        painted = false
        handedOff = false
    }

    /**
     * Late-paint fix (v11): while the native splash is kept, the activity cancels every draw, so the WebView
     * cannot present its first frame (measured: commit +1.1 s but window first frame +2.3 s). The native splash is
     * therefore released as soon as the WebView starts loading; the identical logo cover then stays until commit.
     */
    fun handOffToCover() { handedOff = true }

    fun keepSplash(now: Long): Boolean = shouldKeepSplash(painted || handedOff, now - createdAt)

    fun firstPaint(now: Long, url: String?) {
        if (painted) return
        painted = true
        runCatching { Log.i(TAG, "firstPaint +${now - createdAt}ms ${url?.substringBefore('?')?.take(60)}") }
    }

    val hasPainted: Boolean get() = painted

    companion object {
        const val TAG = "MIStartup"
        const val SPLASH_MAX_MS = 2500L

        fun shouldKeepSplash(painted: Boolean, elapsedMs: Long): Boolean = !painted && elapsedMs < SPLASH_MAX_MS

        /** Hide the cover on commit only for a real https page; the offline-marker check still runs at onPageFinished. */
        fun revealOnCommit(url: String?, readingOldPrivacy: Boolean, errorPending: Boolean): Boolean =
            url != null && !readingOldPrivacy && !errorPending &&
                (url.startsWith("https://") || url.startsWith("file:"))
    }
}
