package app.myinventory.ui.privacy

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect

/**
 * Amounts start hidden on every screen. «نمایش» reveals them for THIS screen only.
 * Not saved: plain remember (not rememberSaveable, not DataStore), and re-hidden on ON_STOP, so leaving the
 * screen, going to background, rotating after process death or reopening the app always shows the mask.
 * Salary is separate: never in any screen payload; fetched from /api/salary on tap and dropped on ON_STOP.
 */
class AmountPrivacy { var revealed by mutableStateOf(false) }

@Composable
fun rememberAmountPrivacy(): AmountPrivacy {
    val p = remember { AmountPrivacy() }
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { p.revealed = false }
    return p
}

/** What a masked amount shows. Units that reveal magnitude («میلیون», «میلیارد») collapse to «تومان» (MaskRules.netUnit). */
fun maskedUnit(revealed: Boolean, unit: String) = if (revealed) unit else "تومان"
