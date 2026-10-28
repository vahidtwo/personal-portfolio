package app.myinventory

/**
 * v11: a main-frame error is not always a failed page. With a service worker answering (cached /dashboard,
 * /offline.html) the WebView can still report a main-frame error, e.g. an offline cold start under navigation
 * preload showed «اتصال به سرور» on v10 although the page was served (Gorg, #44 NO-GO).
 *
 * So a network main-frame error is held, then decided at onPageFinished (or after [DECIDE_AFTER_MS]): it is ignored
 * only if that URL committed (onPageCommitVisible) AND a JS check confirms our page is in the WebView. Otherwise the
 * error screen is shown as before. A served /offline.html counts as served, and the normal finish then runs the
 * offline-marker check, so R2/R2c still fall back to the old host. HTTP errors are only held when they arrive
 * after the commit (a late duplicate); an HTTP error before any commit is acted on at once (v10 behaviour).
 * Pure logic, unit-tested.
 */
class MainFrameErrors {
    private var committed: String? = null
    var pending: String? = null
        private set

    fun started(url: String?) {
        if (!isPendingFor(url)) pending = null // a new navigation drops a stale held error
        committed = null
    }

    fun committed(url: String?) { committed = norm(url) }

    fun wasCommitted(url: String?): Boolean = url != null && committed != null && committed == norm(url)

    /** True = hold the error and decide later; false = show the error screen now. */
    fun holdNetworkError(url: String?, readingOldPrivacy: Boolean): Boolean {
        if (readingOldPrivacy || url == null || !url.startsWith("https://")) return false
        pending = url
        return true
    }

    fun holdHttpError(url: String?, readingOldPrivacy: Boolean): Boolean {
        if (readingOldPrivacy || !wasCommitted(url)) return false
        pending = url
        return true
    }

    fun isPendingFor(url: String?): Boolean = pending != null && norm(pending) == norm(url)

    /** Final decision for the held error; clears it. True = the page was served, ignore the error. */
    fun resolve(jsResult: String?): Boolean {
        val url = pending ?: return true
        pending = null
        return isServed(wasCommitted(url), jsResult)
    }

    companion object {
        const val DECIDE_AFTER_MS = 1500L

        /** "1" only for a real https page of ours (static scripts) or the SW's /offline.html. */
        const val SERVED_JS =
            "(function(){try{return location.protocol==='https:'&&!!document.querySelector(" +
                "'script[src*=\"/static/\"],meta[name=\"x-offline\"]')?'1':'0'}catch(e){return '0'}})()"

        fun isServed(committed: Boolean, jsResult: String?): Boolean = committed && jsResult?.trim() == "\"1\""

        fun norm(url: String?): String? = url?.substringBefore('#')?.trimEnd('/')
    }
}
