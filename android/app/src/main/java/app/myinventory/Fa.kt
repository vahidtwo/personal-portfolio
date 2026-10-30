package app.myinventory

/** Persian text helpers shared by the native screens (pure, unit tested). */
object Fa {
    private const val DIGITS = "۰۱۲۳۴۵۶۷۸۹"

    fun digits(s: String): String = buildString {
        for (c in s) append(if (c in '0'..'9') DIGITS[c - '0'] else c)
    }

    fun minutes(seconds: Int): Int = maxOf(1, (seconds + 59) / 60)

    fun lockedButton(seconds: Int): String = "دوباره امتحان کنید، ${digits(minutes(seconds).toString())} دقیقهٔ دیگر"

    /** True when the text has a Persian/Arabic letter (the password keyboard hint). */
    fun hasPersianLetter(s: String): Boolean = s.any { it in '\u0600'..'\u06FF' && it !in '\u06F0'..'\u06F9' }

    /** «۵ دقیقه پیش» style age for the cached home time. */
    fun ago(ms: Long): String {
        val sec = maxOf(0L, ms / 1000)
        return when {
            sec < 60 -> "لحظاتی پیش"
            sec < 3600 -> "${digits((sec / 60).toString())} دقیقه پیش"
            sec < 86400 -> "${digits((sec / 3600).toString())} ساعت پیش"
            else -> "${digits((sec / 86400).toString())} روز پیش"
        }
    }
}
