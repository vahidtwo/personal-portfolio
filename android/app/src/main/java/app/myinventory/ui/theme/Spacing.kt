package app.myinventory.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

@Immutable
data class Spacing(
    val xxs: Dp = 2.dp,
    val xs: Dp = 4.dp,
    val sm: Dp = 8.dp,
    val md: Dp = 12.dp,
    val lg: Dp = 16.dp,
    val xl: Dp = 20.dp,
    val xxl: Dp = 24.dp,
    val xxxl: Dp = 32.dp,
    val gutter: Dp = 16.dp,        // screen side padding (web width: calc(100% - 32px))
    val cardPadding: Dp = 18.dp,   // public.css .card padding
    val authCardPadding: Dp = 20.dp, // .auth .card 24/20
    val touchMin: Dp = 48.dp,      // every tappable thing
    val fieldHeight: Dp = 52.dp,   // .inp
    val amountFieldHeight: Dp = 60.dp,
    val buttonHeight: Dp = 48.dp,
    val buttonHeightLarge: Dp = 52.dp, // login «ادامه»
    val topBarHeight: Dp = 56.dp,
    val navBarHeight: Dp = 56.dp,  // + navigationBars inset
)
val LocalSpacing = staticCompositionLocalOf { Spacing() }

object Motion {
    const val FAST_MS = 150        // colour/background (web transition .15s)
    const val MEDIUM_MS = 200      // nav indicator, transforms (.2s)
    const val SKELETON_MS = 1400   // shimmer loop (.v2-skel 1.4s)
    const val SPINNER_MS = 800     // .v2-spin .8s
    const val SKELETON_DELAY_MS = 1000L // show skeleton only after 1s (home v2)
}
