package app.myinventory

import android.content.Context
import android.graphics.Canvas
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.view.View
import androidx.core.graphics.PathParser

/**
 * The web bottom bar (partials/main_nav.html + style.css «.main-nav» below 900px), copied for the native home.
 * Same items, order, labels, hrefs and icons (partials/nav_icons.html, 24×24 viewBox, stroke 1.8, round caps).
 */
object WebNav {
    data class Item(val key: String, val label: String, val full: String, val href: String)

    val ITEMS = listOf(
        Item("home", "خانه", "خانه", "/dashboard"),
        Item("assets", "دارایی‌ها", "دارایی‌ها", "/assets"),
        Item("spending", "خرج‌ها", "خرج‌ها", "/dashboard?tab=daily"),
        Item("debts", "بدهی‌ها", "بدهی‌ها و هزینهٔ ماهانه", "/profile?tab=debts"),
        Item("settings", "تنظیمات", "تنظیمات", "/profile?section=settings#account-settings"),
    )

    /** Web tokens: --main-nav-h 56px, pill 58×32, icon 22px, label 12px, gap 3px. */
    const val HEIGHT_DP = 56
    const val PILL_W_DP = 58
    const val PILL_H_DP = 32
    const val ICON_DP = 22
    const val LABEL_LINE_SP = 14.4f
    const val LABEL_LIFT_DP = 1.8f
    const val LABEL_SP = 12f
    const val GAP_DP = 3

    data class Colors(val bg: Int, val border: Int, val fg: Int, val activeFg: Int, val activeIcon: Int, val activeBg: Int, val activeRing: Int)

    /**
     * Dark: --main-nav-bg rgba(9,11,16,.94) on --bg #050608, fg #a3abbe, active text --text #f4f6fb, icon --accent #3ee0b8,
     * pill --accent-muted rgba(62,224,184,.14), ring rgba(62,224,184,.25), border --border rgba(255,255,255,.08).
     * Light: rgba(255,255,255,.94) on #eef1f8, fg --text-muted #5e6678, text #0f1219, icon #0d9f7a,
     * pill rgba(13,159,122,.12), ring rgba(13,159,122,.25), border rgba(20,24,40,.08).
     */
    fun colors(dark: Boolean): Colors = if (dark) Colors(
        bg = 0xF0090B10.toInt(), border = 0x14FFFFFF, fg = 0xFFA3ABBE.toInt(), activeFg = 0xFFF4F6FB.toInt(),
        activeIcon = 0xFF3EE0B8.toInt(), activeBg = 0x243EE0B8, activeRing = 0x403EE0B8,
    ) else Colors(
        bg = 0xF0FFFFFF.toInt(), border = 0x14141828, fg = 0xFF5E6678.toInt(), activeFg = 0xFF0F1219.toInt(),
        activeIcon = 0xFF0D9F7A.toInt(), activeBg = 0x1F0D9F7A, activeRing = 0x400D9F7A,
    )

    /** Icon outlines (stroked) and dots (filled), from nav_icons.html; rect/circle written as path data. */
    data class Icon(val strokes: List<String>, val dots: List<String> = emptyList())

    private fun rect(x: Float, y: Float, w: Float, h: Float, r: Float) =
        "M${x + r},$y H${x + w - r} A$r,$r 0 0 1 ${x + w},${y + r} V${y + h - r} A$r,$r 0 0 1 ${x + w - r},${y + h} " +
            "H${x + r} A$r,$r 0 0 1 $x,${y + h - r} V${y + r} A$r,$r 0 0 1 ${x + r},$y Z"

    private fun circle(cx: Float, cy: Float, r: Float) = "M${cx - r},$cy A$r,$r 0 1 0 ${cx + r},$cy A$r,$r 0 1 0 ${cx - r},$cy Z"

    val ICONS: Map<String, Icon> = mapOf(
        "home" to Icon(listOf("M3.5 10.2 12 3.5l8.5 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-4.2v-5.8H9.2v5.8H5A1.5 1.5 0 0 1 3.5 19z")),
        "assets" to Icon(
            listOf(rect(3f, 6.5f, 18f, 13.5f, 2.5f), "M16.5 6.5V5a1.5 1.5 0 0 0-1.9-1.45L5 6.5", "M21 11h-4a2.25 2.25 0 0 0 0 4.5h4"),
            listOf(circle(16.9f, 13.25f, .6f)),
        ),
        "spending" to Icon(listOf("M6 3.5h12v17l-3-1.8-3 1.8-3-1.8-3 1.8z", "M9 8.5h6M9 12h6M9 15.5h3.5")),
        "debts" to Icon(listOf(rect(3f, 5f, 18f, 14f, 2.5f), "M3 9.5h18M7 14.5h4")),
        "settings" to Icon(listOf("M4 7h9M17 7h3M4 17h3M11 17h9", circle(15f, 7f, 2.2f), circle(9f, 17f, 2.2f))),
    )

    class IconView(context: Context, key: String) : View(context) {
        private val icon = ICONS.getValue(key)
        private val strokes = icon.strokes.map { PathParser.createPathFromPathData(it) }
        private val dots = icon.dots.map { PathParser.createPathFromPathData(it) }
        private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE; strokeWidth = 1.8f; strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND
        }
        private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL }
        private val m = Matrix()
        private val tmp = Path()
        var color: Int = 0
            set(v) { field = v; invalidate() }

        override fun onDraw(canvas: Canvas) {
            val s = width / 24f
            stroke.color = color; fill.color = color
            canvas.save(); canvas.scale(s, s)
            strokes.forEach { canvas.drawPath(it, stroke) }
            dots.forEach { canvas.drawPath(it, fill) }
            canvas.restore()
        }
    }
}
