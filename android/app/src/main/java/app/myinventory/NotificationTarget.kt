package app.myinventory

import android.content.Intent

/** Where a tap on an SMS spend notification lands, through HomeActivity (signed in, after login, or already open). */
object NotificationTarget {
    const val EXTRA = "app.myinventory.OPEN_PATH"
    /** The daily spend list with the «ثبت خرج» form; src=notification makes the web worker load it fresh. */
    const val DAILY = "/dashboard?tab=daily&src=notification"
    /** Same page with the «ثبت خرج» form already open (the spend was not saved or queued). */
    const val ADD = "/dashboard?tab=daily&add=1&src=notification"

    /** Reuse the open HomeActivity (onNewIntent) and drop the WebView pages above it, or start one. */
    const val FLAGS = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP

    enum class Action { NONE, OPEN, AFTER_LOGIN }

    /** Only a path on the app's own origin. */
    fun safePath(raw: String?): String? {
        val p = raw?.trim() ?: return null
        if (!p.startsWith("/") || p.startsWith("//") || p.contains('\\') || p.any { it.isWhitespace() || it.isISOControl() }) return null
        return p
    }

    fun action(path: String?, signedIn: Boolean): Action = when {
        path == null -> Action.NONE
        signedIn -> Action.OPEN
        else -> Action.AFTER_LOGIN
    }
}
