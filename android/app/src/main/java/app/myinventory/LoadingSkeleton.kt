package app.myinventory

import android.content.Context
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.content.res.ColorStateList

/**
 * Phase 4: the cover shown over a WebView tab until its first paint. Grey blocks in the home's
 * colours (light/dark, RTL) plus a small spinner, instead of a blank window.
 */
object LoadingSkeleton {
    fun install(cover: FrameLayout, dark: Boolean) {
        val ctx = cover.context
        val bg = if (dark) 0xFF050608.toInt() else 0xFFEEF1F8.toInt()
        val block = if (dark) 0xFF1B2030.toInt() else 0xFFE6EAF3.toInt()
        val accent = if (dark) 0xFF3EE0B8.toInt() else 0xFF08735A.toInt()
        cover.removeAllViews()
        cover.setBackgroundColor(bg)
        cover.layoutDirection = View.LAYOUT_DIRECTION_RTL
        cover.contentDescription = "در حال بارگذاری"
        val col = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(ctx, 16), dp(ctx, 16), dp(ctx, 16), 0) }
        // title line (start = right in RTL), then cards
        col.addView(bar(ctx, block, 8), LinearLayout.LayoutParams(dp(ctx, 140), dp(ctx, 22)).apply { gravity = Gravity.START })
        for (h in listOf(120, 72, 72, 72, 160)) {
            col.addView(bar(ctx, block, 16), LinearLayout.LayoutParams(-1, dp(ctx, h)).apply { topMargin = dp(ctx, 12) })
        }
        cover.addView(col, FrameLayout.LayoutParams(-1, -1))
        val spin = ProgressBar(ctx).apply { indeterminateTintList = ColorStateList.valueOf(accent) }
        cover.addView(spin, FrameLayout.LayoutParams(dp(ctx, 36), dp(ctx, 36), Gravity.CENTER))
    }

    private fun bar(ctx: Context, color: Int, radius: Int) = View(ctx).apply {
        background = GradientDrawable().apply { setColor(color); cornerRadius = dp(ctx, radius).toFloat() }
    }

    private fun dp(ctx: Context, v: Int) = (v * ctx.resources.displayMetrics.density).toInt()
}
