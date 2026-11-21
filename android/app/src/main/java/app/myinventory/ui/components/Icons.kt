package app.myinventory.ui.components

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/** Line icons on the web's 24×24 grid (partials/nav_icons.html style: stroke 1.8, round caps). Tinted by Icon(). */
object AppIcons {
    private fun rect(x: Float, y: Float, w: Float, h: Float, r: Float) =
        "M${x + r},$y H${x + w - r} A$r,$r 0 0 1 ${x + w},${y + r} V${y + h - r} A$r,$r 0 0 1 ${x + w - r},${y + h} " +
            "H${x + r} A$r,$r 0 0 1 $x,${y + h - r} V${y + r} A$r,$r 0 0 1 ${x + r},$y Z"

    private fun circle(cx: Float, cy: Float, r: Float) =
        "M${cx - r},$cy A$r,$r 0 1 0 ${cx + r},$cy A$r,$r 0 1 0 ${cx - r},$cy Z"

    private fun icon(name: String, vararg strokes: String, dots: List<String> = emptyList()): ImageVector {
        val b = ImageVector.Builder(name = name, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f)
        for (d in strokes) {
            b.addPath(
                pathData = addPathNodes(d), fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 1.8f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
            )
        }
        for (d in dots) b.addPath(pathData = addPathNodes(d), fill = SolidColor(Color.Black))
        return b.build()
    }

    val Home = icon("home", "M3.5 10.2 12 3.5l8.5 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-4.2v-5.8H9.2v5.8H5A1.5 1.5 0 0 1 3.5 19z")
    val Assets = icon(
        "assets", rect(3f, 6.5f, 18f, 13.5f, 2.5f), "M16.5 6.5V5a1.5 1.5 0 0 0-1.9-1.45L5 6.5", "M21 11h-4a2.25 2.25 0 0 0 0 4.5h4",
        dots = listOf(circle(16.9f, 13.25f, .6f)),
    )
    val Spending = icon("spending", "M6 3.5h12v17l-3-1.8-3 1.8-3-1.8-3 1.8z", "M9 8.5h6M9 12h6M9 15.5h3.5")
    val Debts = icon("debts", rect(3f, 5f, 18f, 14f, 2.5f), "M3 9.5h18M7 14.5h4")
    val Settings = icon("settings", "M4 7h9M17 7h3M4 17h3M11 17h9", circle(15f, 7f, 2.2f), circle(9f, 17f, 2.2f))
    val Shield = icon("shield", "M12 3.5 19 6v5.5c0 4.5-3 7.8-7 9-4-1.2-7-4.5-7-9V6z")
    val Logout = icon("logout", "M14 4.5h4.5A1.5 1.5 0 0 1 20 6v12a1.5 1.5 0 0 1-1.5 1.5H14", "M10 8l-4 4 4 4M6 12h9")
    /** Points left: «next» in a right-to-left layout. */
    val Chevron = icon("chev", "M14.5 6 8.5 12l6 6")
    /** Points right: «back» in a right-to-left layout. */
    val Back = icon("back", "M5 12h14M13 6l6 6-6 6")
    val Bell = icon("bell", "M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15z", "M10 20.5a2 2 0 0 0 4 0")
    val Message = icon("sms", "M4.5 5h15A1.5 1.5 0 0 1 21 6.5v9a1.5 1.5 0 0 1-1.5 1.5H10l-4.5 3.5V17h-1A1.5 1.5 0 0 1 3 15.5v-9A1.5 1.5 0 0 1 4.5 5z", "M8 10h8M8 13h5")
    val Lock = icon("lock", rect(5f, 10.5f, 14f, 10f, 2f), "M8 10.5V8a4 4 0 0 1 8 0v2.5")
    val Phone = icon("phone", rect(7f, 3f, 10f, 18f, 2f), "M11 17.5h2")
    val Server = icon("mcp", rect(4f, 4f, 16f, 7f, 2f), rect(4f, 13f, 16f, 7f, 2f), "M8 7.5h.01M8 16.5h.01")
    val Eye = icon("eye", "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z", circle(12f, 12f, 3f))
    val EyeOff = icon("eye-off", "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z", circle(12f, 12f, 3f), "M4 4l16 16")
    val Edit = icon("edit", "M4 20h4L19 9l-4-4L4 16z", "M13.5 6.5l4 4")
    val Alert = icon("alert", circle(12f, 12f, 9f), "M12 7.5v5.5", dots = listOf(circle(12f, 16.2f, 1f)))
    val Check = icon("check", circle(12f, 12f, 9f), "M8 12.2l2.7 2.7L16 9.6")
}
