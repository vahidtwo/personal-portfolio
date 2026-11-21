package app.myinventory

/** Pure rules for the native home's masked mode and chart colours (unit-tested). */
object MaskRules {
    const val MASK = "••••••"

    /** While masked, «میلیون/میلیارد» would give away the order of magnitude: show «تومان» only. */
    fun netUnit(masked: Boolean, unit: String?): String =
        if (masked) "تومان" else unit?.takeIf { it.isNotBlank() } ?: "تومان"

    fun todayLine(masked: Boolean, todayLabel: String): String =
        if (masked) "امروز: $MASK" else "امروز: $todayLabel تومان"

    /** Mini charts follow the trend, not the asset colour (asset colours fail 3:1 on the light card). */
    fun trendColor(kind: String?, dark: Boolean): Int = when (kind) {
        "up" -> if (dark) 0xFF3EE0B8.toInt() else 0xFF08735A.toInt()
        "down" -> if (dark) 0xFFFF8A7A.toInt() else 0xFFB42318.toInt()
        else -> if (dark) 0xFF9AA3B2.toInt() else 0xFF5B6475.toInt()
    }
}

object KeyboardScroll {
    /** [submitBottom] is in scroll-view coordinates (top padding included). scrollY that puts the submit button's bottom plus [margin] at the visible bottom above the keyboard. */
    fun target(submitBottom: Int, margin: Int, scrollHeight: Int, paddingBottom: Int): Int =
        maxOf(0, submitBottom + margin - (scrollHeight - paddingBottom))
}
