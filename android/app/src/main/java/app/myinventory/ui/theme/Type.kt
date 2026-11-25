// Full Vazirmatn static fonts (Arabic + Latin) in res/font, so Latin usernames use Vazirmatn too.
package app.myinventory.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import app.myinventory.R

val Vazirmatn = FontFamily(
    Font(R.font.vazirmatn, FontWeight.Normal),
    Font(R.font.vazirmatn_medium, FontWeight.Medium),
    Font(R.font.vazirmatn_semibold, FontWeight.SemiBold),
    Font(R.font.vazirmatn_bold, FontWeight.Bold),
)

// Persian needs tall lines (web body is 15px / 1.65). No font padding, centred trim so 48dp rows stay centred.
private val Base = TextStyle(
    fontFamily = Vazirmatn,
    textDirection = TextDirection.ContentOrRtl,
    platformStyle = PlatformTextStyle(includeFontPadding = false),
    lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None),
    letterSpacing = 0.em,           // never letter-space Persian (breaks joining)
)
private fun s(size: Int, line: Int, w: FontWeight) = Base.copy(fontSize = size.sp, lineHeight = line.sp, fontWeight = w)

val DaraiitoTypography = Typography(
    displaySmall = s(32, 40, FontWeight.Bold),     // net worth (web clamp(30px, 8.5vw, 46px) ≈ 33 at 390)
    headlineSmall = s(24, 36, FontWeight.Bold),    // login h1 (web 24/800; Vazirmatn web files stop at 700)
    titleLarge = s(22, 32, FontWeight.Bold),       // page title (.page-head h1)
    titleMedium = s(18, 28, FontWeight.SemiBold),  // card + sheet title (.card-head h2, .sp-sheet h2)
    titleSmall = s(16, 24, FontWeight.Bold),       // small card title, empty-state title
    bodyLarge = s(16, 26, FontWeight.Normal),      // text field value (16 = no zoom on web)
    bodyMedium = s(15, 25, FontWeight.Normal),     // body (web 15 / 1.65)
    bodySmall = s(13, 22, FontWeight.Normal),      // hints, muted lines (web 12.5–13.5)
    labelLarge = s(15, 24, FontWeight.Bold),       // buttons (.btn 15/700; login actions 16)
    labelMedium = s(13, 20, FontWeight.SemiBold),  // chips, badges
    labelSmall = s(12, 16, FontWeight.Medium),     // nav labels (--main-nav-label-size 12, line 1.2)
)

@Immutable
data class AmountTypography(
    val large: TextStyle = s(17, 26, FontWeight.Bold),   // tile value (.tile .v)
    val medium: TextStyle = s(15, 24, FontWeight.Bold),  // row value (.acard .vl b 15.5)
    val input: TextStyle = s(22, 32, FontWeight.Bold),   // amount field (.sp-amt input 22/700)
)
val LocalAmountTypography = staticCompositionLocalOf { AmountTypography() }
