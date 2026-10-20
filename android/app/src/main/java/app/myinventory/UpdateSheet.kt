package app.myinventory

import android.annotation.SuppressLint
import android.content.res.Configuration
import android.os.Build
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ImageSpan
import android.view.Gravity
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatDialog
import androidx.core.content.ContextCompat

/** The native bottom sheet (states 1-4 of the approved design). Pure view code. */
class UpdateSheet(
    private val activity: MainActivity,
    private val onPrimary: () -> Unit,
    private val onDismissByUser: () -> Unit,
) {
    enum class Mode { AVAILABLE, DOWNLOADING, READY, FAILED }

    private val dialog = AppCompatDialog(activity, R.style.Theme_MyInventory_UpdateSheet)
    private val root: LinearLayout = LayoutInflater.from(activity).inflate(R.layout.update_sheet, null) as LinearLayout
    private val icon: ImageView = root.findViewById(R.id.sheet_icon)
    private val title: TextView = root.findViewById(R.id.sheet_title)
    private val meta: TextView = root.findViewById(R.id.sheet_meta)
    private val notes: LinearLayout = root.findViewById(R.id.sheet_notes)
    private val chip: TextView = root.findViewById(R.id.sheet_chip)
    private val progressBlock: View = root.findViewById(R.id.sheet_progress_block)
    private val progress: ProgressBar = root.findViewById(R.id.sheet_progress)
    private val percent: TextView = root.findViewById(R.id.sheet_percent)
    private val mb: TextView = root.findViewById(R.id.sheet_mb)
    private val body: TextView = root.findViewById(R.id.sheet_body)
    private val callout: View = root.findViewById(R.id.sheet_callout)
    private val actions: LinearLayout = root.findViewById(R.id.sheet_actions)
    private val primary: Button = root.findViewById(R.id.sheet_primary)
    private val secondary: Button = root.findViewById(R.id.sheet_secondary)
    private val fine: TextView = root.findViewById(R.id.sheet_fine)
    private val scroll: MaxHeightScrollView = root.findViewById(R.id.sheet_scroll)
    private var lastQuarter = -1
    var mode: Mode? = null
        private set

    val isShowing: Boolean get() = dialog.isShowing

    init {
        dialog.setContentView(root)
        dialog.setCancelable(true) // Back
        dialog.setCanceledOnTouchOutside(true) // scrim tap
        dialog.setOnCancelListener { onDismissByUser() }
        dialog.setOnDismissListener { activity.setPageHiddenFromAccessibility(false) }
        primary.setOnClickListener { onPrimary() }
        secondary.setOnClickListener { dialog.cancel() }
        enableSwipeDown(root.findViewById(R.id.sheet_drag))
        enableSwipeDown(root.findViewById(R.id.sheet_header))
    }

    private fun dp(v: Int) = (v * activity.resources.displayMetrics.density).toInt()

    fun show() {
        if (dialog.isShowing) return
        val window = dialog.window ?: return
        val metrics = activity.resources.displayMetrics
        val landscape = activity.resources.configuration.orientation == Configuration.ORIENTATION_LANDSCAPE
        window.setLayout(minOf(metrics.widthPixels, dp(560)), ViewGroup.LayoutParams.WRAP_CONTENT)
        window.setGravity(Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL)
        window.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
        if (metrics.widthPixels / metrics.density <= 370) root.setPaddingRelative(dp(16), 0, dp(16), dp(20))
        // Landscape: buttons side by side and always visible; content scrolls.
        actions.orientation = if (landscape) LinearLayout.HORIZONTAL else LinearLayout.VERTICAL
        listOf(primary, secondary).forEachIndexed { i, b ->
            val lp = b.layoutParams as LinearLayout.LayoutParams
            if (landscape) {
                lp.width = 0; lp.weight = 1f; lp.topMargin = 0; lp.marginStart = if (i == 1) dp(12) else 0
            } else {
                lp.width = ViewGroup.LayoutParams.MATCH_PARENT; lp.weight = 0f
                lp.topMargin = if (i == 1) dp(12) else 0; lp.marginStart = 0
            }
            b.layoutParams = lp
        }
        scroll.maxHeightPx = metrics.heightPixels - dp(16) - dp(if (landscape) 110 else 230)
        activity.setPageHiddenFromAccessibility(true) // focus stays inside the sheet
        dialog.show()
        focusTitle()
    }

    /** Close without counting as «بعداً» (screen change, activity recreated). */
    fun dismissQuietly() {
        if (dialog.isShowing) dialog.dismiss()
    }

    fun cancelByUser() = dialog.cancel()

    fun render(
        newMode: Mode,
        info: UpdateCheck.Info,
        installedCode: Long,
        needsInstallPermission: Boolean,
    ) {
        val changed = newMode != mode
        mode = newMode
        val version = UpdateCheck.fa(info.versionCode.toString())
        val sep = activity.getString(R.string.update_sep)
        val size = UpdateCheck.sizeAbout(info.sizeBytes)
        notes.visibility = View.GONE
        chip.visibility = View.GONE
        progressBlock.visibility = View.GONE
        body.visibility = View.GONE
        callout.visibility = View.GONE
        fine.visibility = View.GONE
        primary.visibility = View.VISIBLE
        primary.contentDescription = null
        root.accessibilityDelegate = null
        when (newMode) {
            Mode.AVAILABLE -> {
                setIcon(R.mipmap.ic_launcher, 0)
                title.setText(R.string.update_available_title)
                meta.text = listOfNotNull(
                    activity.getString(R.string.update_version, version),
                    size,
                    activity.getString(R.string.update_you_have, UpdateCheck.fa(installedCode.toString())),
                ).joinToString(sep)
                fillNotes(info.notes)
                primary.text = withIcon(activity.getString(R.string.update_available_action), R.drawable.ic_update_download)
                primary.contentDescription = activity.getString(R.string.update_available_action_cd, version)
                secondary.setText(R.string.update_later)
                fine.visibility = View.VISIBLE
            }
            Mode.DOWNLOADING -> {
                setIcon(R.mipmap.ic_launcher, 0)
                title.text = activity.getString(R.string.update_downloading_title, version)
                meta.setText(R.string.update_downloading_meta)
                progressBlock.visibility = View.VISIBLE
                if (changed) { lastQuarter = -1; setProgress(0, info.sizeBytes ?: 0) }
                primary.visibility = View.GONE
                secondary.text = withIcon(activity.getString(R.string.update_cancel), R.drawable.ic_update_close)
                secondary.contentDescription = activity.getString(R.string.update_cancel)
            }
            Mode.READY -> {
                setIcon(R.drawable.ic_update_check, R.drawable.update_tile_ok)
                title.setText(R.string.update_ready_title)
                meta.text = activity.getString(R.string.update_ready_meta, version)
                chip.visibility = View.VISIBLE
                body.setText(R.string.update_ready_body)
                body.visibility = View.VISIBLE
                callout.visibility = if (needsInstallPermission) View.VISIBLE else View.GONE
                primary.setText(R.string.update_install)
                secondary.setText(R.string.update_later)
                if (changed) root.announceForAccessibility(activity.getString(R.string.update_announce_ready))
            }
            Mode.FAILED -> {
                setIcon(R.drawable.ic_update_warning, R.drawable.update_tile_bad)
                title.setText(R.string.update_failed_title)
                meta.text = listOfNotNull(activity.getString(R.string.update_version, version), size).joinToString(sep)
                body.setText(R.string.update_failed_body)
                body.visibility = View.VISIBLE
                primary.setText(R.string.update_retry)
                secondary.setText(R.string.update_later)
                if (changed) root.announceForAccessibility(activity.getString(R.string.update_announce_failed))
            }
        }
        if (newMode != Mode.DOWNLOADING) secondary.contentDescription = null
        // failed = alertdialog semantics; the title is the pane's accessible name
        if (Build.VERSION.SDK_INT >= 28) dialog.window?.decorView?.accessibilityPaneTitle = title.text
        dialog.setTitle(title.text)
        if (changed && dialog.isShowing) focusTitle()
    }

    fun setProgress(done: Long, total: Long) {
        val value = UpdateCheck.percentValue(done, total)
        progress.progress = value
        percent.text = UpdateCheck.percent(done, total)
        mb.text = UpdateCheck.progressMb(done, total)
        val label = activity.getString(R.string.update_progress_cd, UpdateCheck.fa(value.toString()))
        progress.contentDescription = label
        if (Build.VERSION.SDK_INT >= 30) progress.stateDescription = label
        val quarter = value / 25
        if (quarter != lastQuarter) { // announce at 25% steps, not every tick
            lastQuarter = quarter
            if (value > 0) progress.announceForAccessibility(label)
        }
    }

    private fun setIcon(res: Int, tile: Int) {
        icon.setImageResource(res)
        if (tile != 0) icon.setBackgroundResource(tile) else icon.background = null
        icon.scaleType = if (tile != 0) ImageView.ScaleType.CENTER else ImageView.ScaleType.FIT_CENTER
    }

    private fun fillNotes(items: List<String>) {
        notes.removeAllViews()
        if (items.isEmpty()) return
        notes.visibility = View.VISIBLE
        items.take(UpdateCheck.MAX_NOTES).forEachIndexed { i, text ->
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                layoutDirection = View.LAYOUT_DIRECTION_RTL
                if (i > 0) setPadding(0, dp(10), 0, 0)
            }
            row.addView(ImageView(activity).apply {
                setImageResource(R.drawable.ic_update_bullet)
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
                layoutParams = LinearLayout.LayoutParams(dp(18), dp(18)).apply { topMargin = dp(4) }
            })
            row.addView(TextView(activity).apply {
                this.text = text
                textSize = 14.5f
                setTextColor(ContextCompat.getColor(activity, R.color.update_text))
                setLineSpacing(0f, 1.3f)
                textAlignment = View.TEXT_ALIGNMENT_VIEW_START
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { marginStart = dp(10) }
            })
            notes.addView(row)
        }
    }

    private fun withIcon(text: String, iconRes: Int): CharSequence {
        val d = ContextCompat.getDrawable(activity, iconRes) ?: return text
        d.setBounds(0, 0, dp(20), dp(20))
        val sb = SpannableStringBuilder(text).append("  ").append(" ")
        val align = if (Build.VERSION.SDK_INT >= 29) ImageSpan.ALIGN_CENTER else ImageSpan.ALIGN_BASELINE
        sb.setSpan(ImageSpan(d, align), sb.length - 1, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        return sb
    }

    private fun focusTitle() {
        title.post {
            title.requestFocus()
            title.performAccessibilityAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS, null)
        }
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun enableSwipeDown(handle: View) {
        var startY = 0f
        var dragging = false
        handle.setOnTouchListener { _, e ->
            when (e.actionMasked) {
                MotionEvent.ACTION_DOWN -> { startY = e.rawY; dragging = true; true }
                MotionEvent.ACTION_MOVE -> {
                    if (dragging) root.translationY = maxOf(0f, e.rawY - startY)
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    val dy = e.rawY - startY
                    dragging = false
                    if (e.actionMasked == MotionEvent.ACTION_UP && dy > dp(80)) {
                        dialog.cancel() // swipe down = «بعداً» / «لغو»
                    } else {
                        root.animate().translationY(0f).setDuration(120).start()
                    }
                    true
                }
                else -> false
            }
        }
    }
}
