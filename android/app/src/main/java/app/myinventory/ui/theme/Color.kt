// Colour tokens from app/static/style.css + public.css. Translucent web values are flattened over their
// usual background, so every token here is opaque. Field borders are raised to 3:1 against the card.
package app.myinventory.ui.theme

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// ---- raw palette ----
internal val DarkBackground = Color(0xFF050608)   // --bg
internal val DarkSurface = Color(0xFF11131A)   // --surface-solid (cards, sheets; web card is translucent + blur)
internal val DarkSurfaceContainerLowest = Color(0xFF0C0E14)   // --bg-elevated (input fill)
internal val DarkSurfaceContainer = Color(0xFF191B22)   // .stat bg rgba(255,255,255,.035) / .6 on card
internal val DarkSurfaceContainerHigh = Color(0xFF1F2128)   // --track
internal val DarkSurfaceContainerHighest = Color(0xFF21232A)   // .v2-skel (text 7%)
internal val DarkOnSurface = Color(0xFFF4F6FB)   // --text
internal val DarkOnSurfaceVariant = Color(0xFFA7AEC0)   // --text-soft
internal val DarkTextMuted = Color(0xFF8B93A8)   // --text-muted (extended)
internal val DarkOutline = Color(0xFF6D6E72)   // --inp-border raised from .22/.28 (web fails 3:1: 1.95/1.86)
internal val DarkOutlineVariant = Color(0xFF24262C)   // --border (card/tile/divider)
internal val DarkPrimary = Color(0xFF3EE0B8)   // --accent-text (text, icons, links, focus ring)
internal val DarkOnPrimary = Color(0xFF04120E)   // ink on primary
internal val DarkAccentFill = Color(0xFF3EE0B8)   // .btn-primary background (extended)
internal val DarkOnAccentFill = Color(0xFF04120E)   // .btn-primary color (extended)
internal val DarkPrimaryContainer = Color(0xFF173030)   // --accent-muted
internal val DarkOnPrimaryContainer = Color(0xFF3EE0B8)   // --accent-text on --accent-muted
internal val DarkSecondaryContainer = Color(0xFF102928)   // --main-nav-active-bg (nav indicator)
internal val DarkOnSecondaryContainer = Color(0xFF3EE0B8)   // --main-nav-active-icon (web light uses #0d9f7a)
internal val DarkNavBar = Color(0xFF090B10)   // --main-nav-bg (extended)
internal val DarkNavFg = Color(0xFFA3ABBE)   // --main-nav-fg (extended)
internal val DarkError = Color(0xFFFF8A80)   // --danger-text
internal val DarkOnError = Color(0xFF1A0503)   // .sp-confirm .btn-danger / .btn-danger
internal val DarkErrorContainer = Color(0xFF2B1513)   // --danger-bg2 (alert)
internal val DarkOnErrorContainer = Color(0xFFF4F6FB)   // .alert color = --text
internal val DarkWarn = Color(0xFFF5B942)   // --warn-text (extended)
internal val DarkWarnContainer = Color(0xFF2A2210)   // --warn-bg2 (extended)
internal val DarkUp = Color(0xFF4ADE80)   // --up (extended)
internal val DarkDown = Color(0xFFFF8A80)   // --danger-text (web delta uses --danger #ff6b5e/#c2410c)
internal val DarkInverseSurface = Color(0xFFF4F6FB)   // snackbar (web .toast is tinted; native uses M3 inverse)
internal val DarkInverseOnSurface = Color(0xFF050608)   // snackbar text
internal val DarkInversePrimary = Color(0xFF08735A)   // snackbar action
internal val LightBackground = Color(0xFFEEF1F8)
internal val LightSurface = Color(0xFFFFFFFF)
internal val LightSurfaceContainerLowest = Color(0xFFFFFFFF)
internal val LightSurfaceContainer = Color(0xFFFFFFFF)
internal val LightSurfaceContainerHigh = Color(0xFFF1F1F2)
internal val LightSurfaceContainerHighest = Color(0xFFEEEEEF)
internal val LightOnSurface = Color(0xFF0F1219)
internal val LightOnSurfaceVariant = Color(0xFF4B5468)
internal val LightTextMuted = Color(0xFF5E6678)
internal val LightOutline = Color(0xFF7E8089)
internal val LightOutlineVariant = Color(0xFFECEDEE)
internal val LightPrimary = Color(0xFF08735A)
internal val LightOnPrimary = Color(0xFFFFFFFF)
internal val LightAccentFill = Color(0xFF0D9F7A)
internal val LightOnAccentFill = Color(0xFF04120E)
internal val LightPrimaryContainer = Color(0xFFE2F3EF)
internal val LightOnPrimaryContainer = Color(0xFF08735A)
internal val LightSecondaryContainer = Color(0xFFE1F3EF)
internal val LightOnSecondaryContainer = Color(0xFF08735A)
internal val LightNavBar = Color(0xFFFEFEFF)
internal val LightNavFg = Color(0xFF5E6678)
internal val LightError = Color(0xFFB42318)
internal val LightOnError = Color(0xFFFFFFFF)
internal val LightErrorContainer = Color(0xFFFDECEA)
internal val LightOnErrorContainer = Color(0xFF0F1219)
internal val LightWarn = Color(0xFF8A4A05)
internal val LightWarnContainer = Color(0xFFFFF6E0)
internal val LightUp = Color(0xFF15803D)
internal val LightDown = Color(0xFFB42318)
internal val LightInverseSurface = Color(0xFF0F1219)
internal val LightInverseOnSurface = Color(0xFFEEF1F8)
internal val LightInversePrimary = Color(0xFF3EE0B8)
internal val UpContainerDark = Color(0xFF132822)
internal val UpContainerLight = Color(0xFFDCFCE7)
internal val DownContainerDark = Color(0xFF291C21)
internal val DownContainerLight = Color(0xFFF9ECE7)
internal val Scrim = Color(0x8C000000) // rgba(0,0,0,.55)
internal val PriceFreshDot = Color(0xFF22C55E)

val DarkColorScheme: ColorScheme = darkColorScheme(
    background = DarkBackground,
    surface = DarkSurface,
    surfaceContainerLowest = DarkSurfaceContainerLowest,
    surfaceContainer = DarkSurfaceContainer,
    surfaceContainerHigh = DarkSurfaceContainerHigh,
    surfaceContainerHighest = DarkSurfaceContainerHighest,
    onSurface = DarkOnSurface,
    onSurfaceVariant = DarkOnSurfaceVariant,
    outline = DarkOutline,
    outlineVariant = DarkOutlineVariant,
    primary = DarkPrimary,
    onPrimary = DarkOnPrimary,
    primaryContainer = DarkPrimaryContainer,
    onPrimaryContainer = DarkOnPrimaryContainer,
    secondaryContainer = DarkSecondaryContainer,
    onSecondaryContainer = DarkOnSecondaryContainer,
    error = DarkError,
    onError = DarkOnError,
    errorContainer = DarkErrorContainer,
    onErrorContainer = DarkOnErrorContainer,
    inverseSurface = DarkInverseSurface,
    inverseOnSurface = DarkInverseOnSurface,
    inversePrimary = DarkInversePrimary,
    onBackground = DarkOnSurface,
    surfaceVariant = DarkSurfaceContainer,
    surfaceContainerLow = DarkSurface,
    surfaceBright = DarkSurfaceContainerHigh,
    surfaceDim = DarkBackground,
    surfaceTint = Color.Transparent,          // web has no tonal tint; keep surfaces neutral
    secondary = DarkOnSurfaceVariant,
    onSecondary = DarkBackground,
    tertiary = DarkWarn,
    onTertiary = DarkBackground,
    tertiaryContainer = DarkWarnContainer,
    onTertiaryContainer = DarkOnSurface,
    scrim = Scrim,
)

val LightColorScheme: ColorScheme = lightColorScheme(
    background = LightBackground,
    surface = LightSurface,
    surfaceContainerLowest = LightSurfaceContainerLowest,
    surfaceContainer = LightSurfaceContainer,
    surfaceContainerHigh = LightSurfaceContainerHigh,
    surfaceContainerHighest = LightSurfaceContainerHighest,
    onSurface = LightOnSurface,
    onSurfaceVariant = LightOnSurfaceVariant,
    outline = LightOutline,
    outlineVariant = LightOutlineVariant,
    primary = LightPrimary,
    onPrimary = LightOnPrimary,
    primaryContainer = LightPrimaryContainer,
    onPrimaryContainer = LightOnPrimaryContainer,
    secondaryContainer = LightSecondaryContainer,
    onSecondaryContainer = LightOnSecondaryContainer,
    error = LightError,
    onError = LightOnError,
    errorContainer = LightErrorContainer,
    onErrorContainer = LightOnErrorContainer,
    inverseSurface = LightInverseSurface,
    inverseOnSurface = LightInverseOnSurface,
    inversePrimary = LightInversePrimary,
    onBackground = LightOnSurface,
    surfaceVariant = LightSurfaceContainer,
    surfaceContainerLow = LightSurface,
    surfaceBright = LightSurfaceContainerHigh,
    surfaceDim = LightBackground,
    surfaceTint = Color.Transparent,          // web has no tonal tint; keep surfaces neutral
    secondary = LightOnSurfaceVariant,
    onSecondary = LightBackground,
    tertiary = LightWarn,
    onTertiary = LightBackground,
    tertiaryContainer = LightWarnContainer,
    onTertiaryContainer = LightOnSurface,
    scrim = Scrim,
)

/** Roles Material 3 has no slot for. Read with DaraiitoTheme.extended. */
@Immutable
data class ExtendedColors(
    val textMuted: Color,
    val accentFill: Color,      // primary button fill (web .btn-primary)
    val onAccentFill: Color,    // #04120e in both themes
    val navBar: Color,
    val navFg: Color,
    val warn: Color,
    val warnContainer: Color,
    val up: Color,
    val upContainer: Color,
    val down: Color,
    val downContainer: Color,
    val priceFresh: Color,
)

val DarkExtended = ExtendedColors(DarkTextMuted, DarkAccentFill, DarkOnAccentFill, DarkNavBar, DarkNavFg, DarkWarn, DarkWarnContainer, DarkUp, UpContainerDark, DarkDown, DownContainerDark, PriceFreshDot)
val LightExtended = ExtendedColors(LightTextMuted, LightAccentFill, LightOnAccentFill, LightNavBar, LightNavFg, LightWarn, LightWarnContainer, LightUp, UpContainerLight, LightDown, DownContainerLight, PriceFreshDot)

val LocalExtendedColors = staticCompositionLocalOf { DarkExtended }
