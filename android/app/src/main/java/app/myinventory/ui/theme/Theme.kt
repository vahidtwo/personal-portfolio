package app.myinventory.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection

/**
 * Theme follows the system (the web follows `inventory-theme` or prefers-color-scheme).
 * No dynamic colour: the brand teal must not change with the wallpaper.
 * The whole app is RTL regardless of the device locale (an English-locale phone still gets RTL Persian UI).
 */
@Composable
fun DaraiitoTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val scheme = if (darkTheme) DarkColorScheme else LightColorScheme
    val extended = if (darkTheme) DarkExtended else LightExtended
    CompositionLocalProvider(
        LocalLayoutDirection provides LayoutDirection.Rtl,
        LocalExtendedColors provides extended,
        LocalSpacing provides Spacing(),
        LocalAmountTypography provides AmountTypography(),
    ) {
        MaterialTheme(
            colorScheme = scheme,
            typography = DaraiitoTypography,
            shapes = DaraiitoShapes,
            content = content,
        )
    }
}

object DaraiitoTheme {
    val extended: ExtendedColors @Composable @ReadOnlyComposable get() = LocalExtendedColors.current
    val spacing: Spacing @Composable @ReadOnlyComposable get() = LocalSpacing.current
    val amount: AmountTypography @Composable @ReadOnlyComposable get() = LocalAmountTypography.current
}

/** Bottom sheet scrim: black at 55%. */
val SheetScrim: androidx.compose.ui.graphics.Color get() = Scrim
