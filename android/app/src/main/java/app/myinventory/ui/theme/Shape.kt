package app.myinventory.ui.theme

import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.ui.unit.dp

val DaraiitoShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),   // badge (6 on web), focus ring corner
    small = RoundedCornerShape(12.dp),       // stat tile, icon button, snackbar
    medium = RoundedCornerShape(14.dp),      // text field, alert/banner, tile, list step
    large = RoundedCornerShape(20.dp),       // card
    extraLarge = RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp), // bottom sheet top
)
val PillShape = CircleShape                  // buttons, chips, segmented tabs, nav indicator (web 999px)
