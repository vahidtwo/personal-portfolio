package app.myinventory.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.semantics.error
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import app.myinventory.ui.format.AmountVisualTransformation
import app.myinventory.ui.format.MASK
import app.myinventory.ui.format.amountWordsLine
import app.myinventory.ui.theme.DaraiitoTheme
import app.myinventory.ui.theme.Motion
import app.myinventory.ui.theme.PillShape

/**
 * Money is never truncated: one line, no wrap, shrinking in 1sp steps from [maxSize] to [minSize].
 * Below that it stays at [minSize] and overflows visibly rather than hiding the leading digits.
 */
@Composable
fun AmountText(
    text: String, style: TextStyle, modifier: Modifier = Modifier,
    maxSize: TextUnit = 17.sp, minSize: TextUnit = 13.sp, color: Color = Color.Unspecified,
) {
    val measurer = rememberTextMeasurer()
    BoxWithConstraints(modifier) {
        val width = constraints.maxWidth
        var size = maxSize.value
        if (constraints.hasBoundedWidth) {
            while (size > minSize.value &&
                measurer.measure(text, style.copy(fontSize = size.sp), maxLines = 1, softWrap = false).size.width > width) {
                size -= 1f
            }
        }
        Text(
            text, style = style.copy(fontSize = size.sp, textDirection = TextDirection.Ltr), color = color,
            maxLines = 1, softWrap = false, overflow = TextOverflow.Visible,
        )
    }
}

/** 48dp pill, accent fill (web .btn-primary). Shows a spinner instead of the label while [busy]. */
@Composable
fun PrimaryButton(
    text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, busy: Boolean = false,
    icon: ImageVector? = null,
) {
    val ext = DaraiitoTheme.extended
    val cs = MaterialTheme.colorScheme
    Button(
        onClick = onClick, enabled = enabled && !busy, shape = PillShape,
        modifier = modifier.heightIn(min = DaraiitoTheme.spacing.buttonHeight),
        colors = ButtonDefaults.buttonColors(
            containerColor = ext.accentFill, contentColor = ext.onAccentFill,
            disabledContainerColor = if (busy) ext.accentFill else cs.surfaceContainerHighest,
            disabledContentColor = if (busy) ext.onAccentFill else ext.textMuted,
        ),
    ) {
        if (busy) Spinner(color = ext.onAccentFill) else {
            if (icon != null) {
                Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
            }
            Text(text, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/** 48dp pill with a 1dp outline (web .btn-ghost). */
@Composable
fun SecondaryButton(
    text: String, onClick: () -> Unit, modifier: Modifier = Modifier, icon: ImageVector? = null,
    enabled: Boolean = true, busy: Boolean = false, accent: Boolean = false, busyLabel: Boolean = false,
) {
    val cs = MaterialTheme.colorScheme
    val fg = if (accent) cs.primary else cs.onSurface
    OutlinedButton(
        onClick = onClick, enabled = enabled && !busy, shape = PillShape,
        modifier = modifier.heightIn(min = DaraiitoTheme.spacing.buttonHeight),
        border = BorderStroke(1.dp, if (accent) cs.primary else cs.outline),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = fg),
        contentPadding = PaddingValues(horizontal = 18.dp),
    ) {
        if (busy) {
            Spinner(color = fg)
            if (busyLabel) { Spacer(Modifier.width(8.dp)); Text(text, style = MaterialTheme.typography.labelLarge) }
        } else {
            if (icon != null) {
                Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
            }
            Text(text, style = MaterialTheme.typography.labelLarge)
        }
    }
}

/** Destructive confirm (logout): error fill. */
@Composable
fun DangerButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, busy: Boolean = false) {
    val cs = MaterialTheme.colorScheme
    Button(
        onClick = onClick, enabled = !busy, shape = PillShape,
        modifier = modifier.heightIn(min = DaraiitoTheme.spacing.buttonHeight),
        colors = ButtonDefaults.buttonColors(containerColor = cs.error, contentColor = cs.onError),
    ) { if (busy) Spinner(color = cs.onError) else Text(text, style = MaterialTheme.typography.labelLarge) }
}

@Composable
fun Spinner(modifier: Modifier = Modifier, color: Color = MaterialTheme.colorScheme.primary, size: Dp = 20.dp) {
    CircularProgressIndicator(modifier = modifier.size(size), color = color, strokeWidth = 2.dp)
}

/** Label above, 52dp field, hint or error below (error replaces the hint and is announced). */
@Composable
fun LabeledField(
    label: String, value: String, onValueChange: (String) -> Unit, modifier: Modifier = Modifier,
    hint: String? = null, error: String? = null, ltr: Boolean = false, keyboardType: KeyboardType = KeyboardType.Text,
    password: Boolean = false, enabled: Boolean = true, trailing: (@Composable () -> Unit)? = null,
    visualTransformation: VisualTransformation = VisualTransformation.None, textStyle: TextStyle = MaterialTheme.typography.bodyLarge,
    height: Dp = DaraiitoTheme.spacing.fieldHeight, align: TextAlign? = null, placeholder: String? = null,
    below: (@Composable () -> Unit)? = null,
) {
    val cs = MaterialTheme.colorScheme
    var shown by rememberSaveable { mutableStateOf(false) }
    Column(modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.labelLarge, color = cs.onSurface)
        Spacer(Modifier.height(8.dp))
        val style = (if (ltr) textStyle.copy(textDirection = TextDirection.Ltr, textAlign = TextAlign.Left) else textStyle)
            .let { if (align != null) it.copy(textAlign = align) else it }
        OutlinedTextField(
            value = value, onValueChange = onValueChange, singleLine = true, enabled = enabled,
            isError = error != null, textStyle = style,
            modifier = Modifier.fillMaxWidth().heightIn(min = height)
                .then(if (error != null) Modifier.border(2.dp, cs.error, MaterialTheme.shapes.medium) else Modifier)
                .semantics {
                    contentDescription = label
                    if (error != null) error(error)
                },
            placeholder = placeholder?.let { p -> { Text(p, style = style, color = DaraiitoTheme.extended.textMuted, modifier = Modifier.fillMaxWidth()) } },
            shape = MaterialTheme.shapes.medium,
            keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboardType, autoCorrectEnabled = false),
            visualTransformation = if (password && !shown) PasswordVisualTransformation() else visualTransformation,
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = cs.primary, unfocusedBorderColor = cs.outline, errorBorderColor = cs.error,
                focusedContainerColor = cs.surfaceContainerLowest, unfocusedContainerColor = cs.surfaceContainerLowest,
                errorContainerColor = cs.surfaceContainerLowest, cursorColor = cs.primary,
            ),
            trailingIcon = when {
                password -> {
                    {
                        TextButton(onClick = { shown = !shown }, modifier = Modifier.heightIn(min = 48.dp)) {
                            Icon(if (shown) AppIcons.EyeOff else AppIcons.Eye, contentDescription = null, modifier = Modifier.size(18.dp), tint = cs.primary)
                            Spacer(Modifier.width(4.dp))
                            Text(if (shown) "پنهان" else "نمایش", style = MaterialTheme.typography.labelMedium, color = cs.primary)
                        }
                    }
                }
                trailing != null -> trailing
                else -> null
            },
        )
        below?.invoke()
        when {
            error != null -> Row(
                Modifier.padding(top = 6.dp).semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(AppIcons.Alert, contentDescription = null, tint = cs.error, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(error, style = MaterialTheme.typography.bodySmall, color = cs.error)
            }
            hint != null -> Text(
                hint, style = MaterialTheme.typography.bodySmall, color = DaraiitoTheme.extended.textMuted,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

/** Amount input: Latin digits stored, «۴۸٬۰۰۰٬۰۰۰» shown, «تومان» at the end. Empty on open; never prefilled with money. */
@Composable
fun AmountField(label: String, value: String, onValueChange: (String) -> Unit, hint: String? = null, error: String? = null) {
    val words = amountWordsLine(value)
    LabeledField(
        label = label, value = value,
        onValueChange = { raw -> onValueChange(amountDigits(raw)) },
        hint = hint ?: "به تومان؛ فقط عدد", error = error, ltr = true, keyboardType = KeyboardType.Number,
        visualTransformation = AmountVisualTransformation, textStyle = DaraiitoTheme.amount.input,
        height = DaraiitoTheme.spacing.amountFieldHeight, align = TextAlign.Right, placeholder = "۰",
        trailing = {
            Text("تومان", style = MaterialTheme.typography.bodyMedium, color = DaraiitoTheme.extended.textMuted,
                modifier = Modifier.padding(horizontal = 12.dp))
        },
        below = if (words != null && error == null) {
            {
                Text(words, style = MaterialTheme.typography.bodySmall.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold),
                    color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 6.dp))
            }
        } else null,
    )
}

/** Keeps only digits (Persian/Arabic digits become Latin), at most 15. Pure; unit tested. */
fun amountDigits(raw: String): String = raw.mapNotNull { c ->
    when (c) {
        in '0'..'9' -> c
        in '۰'..'۹' -> '0' + (c - '۰')
        in '٠'..'٩' -> '0' + (c - '٠')
        else -> null
    }
}.joinToString("").trimStart('0').ifEmpty { if (raw.any { it == '0' || it == '۰' || it == '٠' }) "0" else "" }.take(15)

enum class AlertKind { Error, Success, Info }

/** Banner inside a card: icon, bold title, optional detail. Announced politely. */
@Composable
fun AlertBox(kind: AlertKind, title: String, detail: String? = null, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    val (bg, fg, icon) = when (kind) {
        AlertKind.Error -> Triple(cs.errorContainer, cs.error, AppIcons.Alert)
        AlertKind.Success -> Triple(cs.primaryContainer, cs.primary, AppIcons.Check)
        AlertKind.Info -> Triple(cs.surfaceContainerHigh, cs.onSurfaceVariant, AppIcons.Alert)
    }
    Row(
        modifier.fillMaxWidth().background(bg, MaterialTheme.shapes.medium).padding(14.dp)
            .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
        verticalAlignment = Alignment.Top,
    ) {
        Icon(icon, contentDescription = null, tint = fg, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = cs.onErrorContainer)
            if (!detail.isNullOrEmpty()) Text(detail, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
        }
    }
}

/** Grey placeholder block with the web's slow pulse. */
@Composable
fun SkeletonBlock(modifier: Modifier = Modifier, height: Dp = 16.dp, radius: Dp = 8.dp) {
    val t = rememberInfiniteTransition(label = "skel")
    val a by t.animateFloat(.55f, 1f, infiniteRepeatable(tween(Motion.SKELETON_MS / 2), RepeatMode.Reverse), label = "skelA")
    Box(modifier.height(height).alpha(a).background(MaterialTheme.colorScheme.surfaceContainerHighest, RoundedCornerShape(radius)))
}

/** Card surface: radius 20, 1dp outlineVariant. */
@Composable
fun AppCard(modifier: Modifier = Modifier, padding: Dp = DaraiitoTheme.spacing.cardPadding, content: @Composable ColumnScope.() -> Unit) {
    val cs = MaterialTheme.colorScheme
    val light = cs.background.luminance() > .5f
    Column(
        modifier.fillMaxWidth()
            .then(if (light) Modifier.shadow(2.dp, MaterialTheme.shapes.large) else Modifier)
            .background(cs.surface, MaterialTheme.shapes.large)
            .border(1.dp, cs.outlineVariant, MaterialTheme.shapes.large).padding(padding),
        content = content,
    )
}

@Composable
fun SectionLabel(text: String) {
    Text(
        text, style = MaterialTheme.typography.bodySmall, color = DaraiitoTheme.extended.textMuted,
        modifier = Modifier.padding(start = 4.dp, top = 20.dp, bottom = 8.dp).semantics { heading() },
    )
}

/** Rows separated by dividers inset 16dp, inside an [AppCard] without padding. */
@Composable
fun ListCard(rows: List<@Composable () -> Unit>) {
    AppCard(padding = 0.dp) {
        rows.forEachIndexed { i, row ->
            if (i > 0) HorizontalDivider(Modifier.padding(horizontal = 16.dp), color = MaterialTheme.colorScheme.outlineVariant)
            row()
        }
    }
}

/** 56dp row (64 with a supporting line): tonal icon box, headline, supporting, trailing value, chevron. */
@Composable
fun SettingsListItem(
    icon: ImageVector, headline: String, supporting: String? = null, trailing: String? = null,
    showChevron: Boolean = true, danger: Boolean = false, onClick: (() -> Unit)? = null,
) {
    val cs = MaterialTheme.colorScheme
    val tint = if (danger) cs.error else cs.onSurfaceVariant
    val base = Modifier.fillMaxWidth().heightIn(min = if (supporting != null) 64.dp else 56.dp)
    Row(
        (if (onClick != null) base.clickable(role = Role.Button, onClick = onClick) else base.semantics(mergeDescendants = true) {})
            .padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(40.dp).background(cs.surfaceContainerHigh, MaterialTheme.shapes.small), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(22.dp))
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(headline, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold),
                color = if (danger) cs.error else cs.onSurface)
            if (supporting != null) {
                Text(supporting, style = MaterialTheme.typography.bodySmall, color = DaraiitoTheme.extended.textMuted, maxLines = 2)
            }
        }
        if (trailing != null) {
            Spacer(Modifier.width(8.dp))
            Text(trailing, style = MaterialTheme.typography.bodySmall, color = DaraiitoTheme.extended.textMuted,
                modifier = if (trailing == MASK) Modifier.semantics { contentDescription = "پنهان" } else Modifier)
        }
        if (showChevron && onClick != null) {
            Spacer(Modifier.width(6.dp))
            Icon(AppIcons.Chevron, contentDescription = null, tint = DaraiitoTheme.extended.textMuted, modifier = Modifier.size(18.dp))
        }
    }
}

data class ThemeOption(val key: String, val label: String, val sub: String? = null)

/** Three equal 64dp radio cards; the selected one has a 2dp primary border on primaryContainer. */
@Composable
fun ThemeRadioCards(options: List<ThemeOption>, selected: String, onSelect: (String) -> Unit) {
    val cs = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth().selectableGroup(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        for (o in options) {
            val on = o.key == selected
            Column(
                Modifier.weight(1f).heightIn(min = 64.dp)
                    .background(if (on) cs.primaryContainer else cs.surface, RoundedCornerShape(16.dp))
                    .border(if (on) 2.dp else 1.dp, if (on) cs.primary else cs.outline, RoundedCornerShape(16.dp))
                    .selectable(selected = on, role = Role.RadioButton, onClick = { onSelect(o.key) })
                    .padding(vertical = 10.dp, horizontal = 6.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
            ) {
                Text(o.label, style = MaterialTheme.typography.labelLarge, color = cs.onSurface)
                if (o.sub != null) Text(o.sub, style = MaterialTheme.typography.bodySmall, color = DaraiitoTheme.extended.textMuted)
            }
        }
    }
}

/** 56dp bar: back arrow at the start (right in RTL) when [onBack] is set, then the title. */
@Composable
fun TopBar(title: String, onBack: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().height(DaraiitoTheme.spacing.topBarHeight).padding(horizontal = if (onBack != null) 4.dp else 16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) {
            IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) {
                Icon(AppIcons.Back, contentDescription = "بازگشت", tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Spacer(Modifier.width(4.dp))
        }
        Text(title, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSurface,
            modifier = Modifier.semantics { heading() })
    }
}

data class NavItem(val key: String, val label: String, val full: String, val icon: ImageVector)

val NAV_ITEMS = listOf(
    NavItem("home", "خانه", "خانه", AppIcons.Home),
    NavItem("assets", "دارایی‌ها", "دارایی‌ها", AppIcons.Assets),
    NavItem("spending", "خرج‌ها", "خرج‌ها", AppIcons.Spending),
    NavItem("debts", "بدهی‌ها", "بدهی‌ها و هزینهٔ ماهانه", AppIcons.Debts),
    NavItem("settings", "تنظیمات", "تنظیمات", AppIcons.Settings),
)

/** The web bottom bar: 56dp, 58×32 pill behind the active icon, 12sp labels; plus the navigation-bar inset. */
@Composable
fun BottomNav(active: String, onSelect: (String) -> Unit) {
    val ext = DaraiitoTheme.extended
    val cs = MaterialTheme.colorScheme
    Column(Modifier.fillMaxWidth().background(ext.navBar)) {
        HorizontalDivider(color = cs.outlineVariant)
        Row(Modifier.fillMaxWidth().navigationBarsPadding().height(DaraiitoTheme.spacing.navBarHeight)
            .semantics { contentDescription = "بخش‌های اصلی" }) {
            for (item in NAV_ITEMS) {
                val on = item.key == active
                Column(
                    Modifier.weight(1f).height(56.dp)
                        .clickable(role = Role.Tab) { onSelect(item.key) }
                        .semantics(mergeDescendants = true) {
                            contentDescription = item.full
                            if (on) stateDescription = "صفحهٔ فعلی"
                        },
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                ) {
                    Box(
                        Modifier.size(58.dp, 32.dp).then(
                            if (on) Modifier.background(cs.secondaryContainer, RoundedCornerShape(16.dp)) else Modifier,
                        ),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(item.icon, contentDescription = null, tint = if (on) cs.onSecondaryContainer else ext.navFg, modifier = Modifier.size(22.dp))
                    }
                    Spacer(Modifier.height(3.dp))
                    Text(item.label, style = MaterialTheme.typography.labelSmall.copy(
                        fontWeight = if (on) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Medium),
                        color = if (on) cs.onSurface else ext.navFg, maxLines = 1)
                }
            }
        }
    }
}

/** Letter avatar, 44dp accent circle. */
@Composable
fun LetterAvatar(letter: String) {
    val ext = DaraiitoTheme.extended
    Box(Modifier.size(44.dp).background(ext.accentFill, CircleShape), contentAlignment = Alignment.Center) {
        Text(letter, style = MaterialTheme.typography.titleMedium, color = ext.onAccentFill)
    }
}


/**
 * Cancel then action. Side by side in a right-to-left row (cancel on the right, action on the left);
 * stacked full width, action on top, when large text would wrap the labels.
 */
@Composable
fun ButtonPair(cancel: (@Composable (Modifier) -> Unit)?, action: @Composable (Modifier) -> Unit) {
    if (androidx.compose.ui.platform.LocalDensity.current.fontScale > 1.15f) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            action(Modifier.fillMaxWidth())
            cancel?.invoke(Modifier.fillMaxWidth())
        }
    } else {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            cancel?.invoke(Modifier.weight(1f))
            action(Modifier.weight(1f))
        }
    }
}
