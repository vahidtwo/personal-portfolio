package app.myinventory

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import androidx.core.app.ActivityCompat

/** Native SMS settings (spec: /mockups/sms-permission). Keywords never reach the WebView. */
class SmsSettingsActivity : Activity() {
    private lateinit var root: LinearLayout
    private var deniedOnce = false
    private var errorText: String? = null
    private var errorOnInput = false
    private var draft = ""

    private val bg = Color.parseColor("#0f1118")
    private val card = Color.parseColor("#181b25")
    private val cText = Color.parseColor("#e8eaf0")
    private val muted = Color.parseColor("#8b93a8")
    private val accent = Color.parseColor("#2fd3a6")
    private val danger = Color.parseColor("#ff8a7a")
    private val amber = Color.parseColor("#f5b94a")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        title = "تنظیمات پیامک"
        window.decorView.layoutDirection = View.LAYOUT_DIRECTION_RTL
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(16), dp(16), dp(32)) }
        setContentView(ScrollView(this).apply { setBackgroundColor(bg); isFillViewport = true; addView(root) })
        SmsPrefs.ensureMigrated(this)
    }

    override fun onResume() { super.onResume(); render() } // re-check permission after app settings

    private fun permanentlyDenied(): Boolean =
        SmsPrefs.askedBefore(this) && !SmsPrefs.permissionGranted(this) &&
            !ActivityCompat.shouldShowRequestPermissionRationale(this, Manifest.permission.RECEIVE_SMS)

    private fun render() {
        root.removeAllViews()
        if (SmsPrefs.upgradeNotePending(this)) root.addView(upgradeCard())
        root.addView(tv("خرج‌ها", 20f, cText, bold = true).apply { contentDescription = "خرج‌ها"; accessibilityHeading() })
        val granted = SmsPrefs.permissionGranted(this)
        val denied = !granted && permanentlyDenied()
        val on = SmsPrefs.isEnabledPref(this) && granted
        val box = section()
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; minimumHeight = dp(52) }
        val label = tv("ثبت خودکار خرج از پیامک", 16f, cText, bold = true).apply { layoutParams = LinearLayout.LayoutParams(0, -2, 1f) }
        val sw = Switch(this).apply {
            isChecked = on; isEnabled = !denied; contentDescription = "ثبت خودکار خرج از پیامک"
            minimumHeight = dp(44); minimumWidth = dp(52)
            setOnClickListener { onToggle(isChecked) }
        }
        row.addView(label); row.addView(sw)
        if (!denied) row.setOnClickListener { sw.isChecked = !sw.isChecked; onToggle(sw.isChecked) }
        box.addView(row)
        val explainer = when {
            denied -> "خاموش است، چون اجازهٔ پیامک داده نشده."
            on -> "روشن است. پیامک‌های تازه‌ای که یکی از کلمه‌های زیر و یک مبلغ را دارند، خرج ثبت می‌شوند."
            else -> "پیامک‌های تازه‌ای که «${firstKeyword()}» و یک مبلغ دارند، خودکار به‌عنوان خرج ثبت می‌شوند."
        }
        box.addView(tv(explainer, 14f, muted))
        if (deniedOnce && !on && !denied) box.addView(tv("اجازه داده نشد.", 14f, danger))
        root.addView(box)
        if (denied) root.addView(deniedBox())
        if (on) root.addView(keywordSection())
    }

    private fun firstKeyword() = SmsPrefs.keywords(this).first()

    private fun onToggle(wantOn: Boolean) {
        if (!wantOn) { SmsPrefs.setEnabled(this, false); render(); return }
        when {
            SmsPrefs.permissionGranted(this) -> { SmsPrefs.setEnabled(this, true); render() }
            permanentlyDenied() -> render()
            else -> { render(); showPrePermissionSheet() }
        }
    }

    private fun showPrePermissionSheet() {
        val v = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(16), dp(20), dp(8)); layoutDirection = View.LAYOUT_DIRECTION_RTL }
        val kw = firstKeyword()
        v.addView(tv("اگر اجازه دهید، وقتی پیامکی با «$kw» و یک مبلغ می‌رسد، اپ خودش آن را خرج ثبت می‌کند.", 15f, cText))
        v.addView(tv("چه چیزی خوانده می‌شود", 15f, cText, bold = true).apply { accessibilityHeading() })
        v.addView(bullet("فقط پیامک‌های تازه، از همین حالا به بعد. پیامک‌های قبلی صندوق خوانده نمی‌شوند."))
        v.addView(bullet("فقط پیامک‌هایی که «$kw» (یا کلمه‌هایی که خودتان اضافه می‌کنید) و یک مبلغ دارند. بقیه نادیده گرفته می‌شوند. کلمه‌ها فقط روی گوشی می‌مانند."))
        v.addView(tv("چه چیزی به سایت فرستاده می‌شود", 15f, cText, bold = true).apply { accessibilityHeading() })
        v.addView(bullet("مبلغ به تومان"))
        v.addView(bullet("یادداشتی کوتاه: ۱۰۰ حرف اول پیامک، با شمارهٔ کارت یا حساب به شکل **** و بدون مانده"))
        v.addView(bullet("یک کد برای اینکه یک خرج دو بار ثبت نشود"))
        v.addView(bullet("شمارهٔ فرستندهٔ پیامک فرستاده نمی‌شود. اپ هم نمی‌تواند پیامک بفرستد."))
        v.addView(tv("بعد از این، اندروید هم اجازه را می‌پرسد. هر وقت بخواهید، از تنظیمات خاموش می‌شود.", 13f, muted))
        val dlg = AlertDialog.Builder(this)
            .setTitle("خرج‌ها را خودکار ثبت کنیم؟")
            .setView(ScrollView(this).apply { addView(v) })
            .setPositiveButton("اجازه می‌دهم") { _, _ ->
                SmsPrefs.markAsked(this)
                ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECEIVE_SMS), REQ_SMS)
            }
            .setNegativeButton("فعلاً نه") { _, _ -> render() }
            .setOnCancelListener { render() }
            .create()
        dlg.show()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQ_SMS) return
        val ok = grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED
        SmsPrefs.setEnabled(this, ok)
        deniedOnce = !ok
        render()
    }

    private fun deniedBox(): View = section(amber).apply {
        addView(tv("اجازهٔ پیامک داده نشده", 15f, amber, bold = true))
        addView(tv("اندروید دیگر از شما نمی‌پرسد. برای روشن کردن، در تنظیمات برنامه بخش «مجوزها» را باز کنید و «پیامک» را اجازه دهید، بعد برگردید.", 14f, cText))
        addView(button("باز کردن تنظیمات برنامه") {
            SmsPrefs.setEnabled(this@SmsSettingsActivity, true)
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", packageName, null)))
        })
    }

    private fun upgradeCard(): View = section(accent).apply {
        contentDescription = null
        addView(tv("از این نسخه فقط پیامک‌هایی ثبت می‌شوند که یکی از کلمه‌های شما را دارند. کلمهٔ «برداشت» را برایتان اضافه کردیم؛ در تنظیمات می‌توانید عوضش کنید.", 14f, cText))
        addView(button("باشه") { SmsPrefs.dismissUpgradeNote(this@SmsSettingsActivity); render() })
    }

    private fun keywordSection(): View {
        val s = section()
        val list = SmsPrefs.keywords(this)
        s.addView(tv("کلمه‌های پیامک", 15f, cText, bold = true).apply { accessibilityHeading() })
        val flow = FlowLayout(this, dp(12)).apply { contentDescription = "کلمه‌های پیامک" }
        list.forEach { w -> flow.addView(chip(w, list.size == 1)) }
        s.addView(flow)
        if (errorText != null && !errorOnInput) s.addView(alert(errorText!!))
        val addRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val input = EditText(this).apply {
            hint = "کلمهٔ تازه، مثلاً پرداخت"; setText(draft); setSingleLine(); ellipsize = TextUtils.TruncateAt.END
            contentDescription = "کلمهٔ تازه"; setTextColor(if (errorOnInput) danger else cText); setHintTextColor(muted)
            imeOptions = EditorInfo.IME_ACTION_DONE
            layoutParams = LinearLayout.LayoutParams(0, dp(48), 1f)
            tag = "sms-keyword-input"
        }
        val add = button("افزودن") { addKeyword(input) }
        input.setOnEditorActionListener { _, id, ev ->
            if (id == EditorInfo.IME_ACTION_DONE || ev?.keyCode == KeyEvent.KEYCODE_ENTER) { addKeyword(input); true } else false
        }
        addRow.addView(input); addRow.addView(add)
        s.addView(addRow)
        if (errorText != null && errorOnInput) s.addView(alert(errorText!!))
        s.addView(tv("پیامکی ثبت می‌شود که یکی از این کلمه‌ها و یک مبلغ را داشته باشد.", 13f, muted))
        s.addView(tv("این کلمه‌ها فقط روی همین گوشی ذخیره می‌شوند و به سایت فرستاده نمی‌شوند.", 13f, muted))
        s.addView(tv("اجازهٔ پیامک داده شده", 13f, accent))
        return s
    }

    private fun addKeyword(input: EditText) {
        draft = input.text.toString()
        when (val r = SmsKeywords.add(SmsPrefs.keywords(this), draft)) {
            is SmsKeywords.AddResult.Empty -> return
            is SmsKeywords.AddResult.Duplicate -> { errorText = "این کلمه را قبلاً اضافه کرده‌اید"; errorOnInput = true }
            is SmsKeywords.AddResult.Added -> {
                SmsPrefs.saveKeywords(this, r.list); draft = ""; errorText = null
                root.announceForAccessibility("کلمهٔ ${r.list.last()} اضافه شد")
            }
        }
        render()
        root.findViewWithTag<EditText>("sms-keyword-input")?.requestFocus()
    }

    private fun chip(word: String, last: Boolean): View {
        val c = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL
            background = round(Color.parseColor("#232838"), dp(22)); setPadding(dp(14), 0, dp(2), 0)
        }
        c.addView(tv(word, 15f, cText).apply { maxWidth = dp(220); setSingleLine(); ellipsize = TextUtils.TruncateAt.END; setPadding(0, 0, 0, 0) })
        val x = ImageButton(this).apply {
            setImageResource(android.R.drawable.ic_menu_close_clear_cancel); setBackgroundColor(Color.TRANSPARENT)
            contentDescription = "حذف کلمهٔ $word"; layoutParams = LinearLayout.LayoutParams(dp(44), dp(44))
            alpha = if (last) 0.4f else 1f
            setOnClickListener {
                when (val r = SmsKeywords.remove(SmsPrefs.keywords(this@SmsSettingsActivity), word)) {
                    is SmsKeywords.RemoveResult.LastOneBlocked -> {
                        errorText = "دست‌کم یک کلمه لازم است؛ وگرنه هیچ پیامکی ثبت نمی‌شود. اول کلمهٔ دیگری اضافه کنید، بعد این را حذف کنید."
                        errorOnInput = false
                    }
                    is SmsKeywords.RemoveResult.Removed -> { SmsPrefs.saveKeywords(this@SmsSettingsActivity, r.list); errorText = null }
                    else -> {}
                }
                render()
                if (errorText != null) root.announceForAccessibility(errorText)
            }
        }
        c.addView(x)
        return c
    }

    // --- small view helpers ---
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun round(color: Int, r: Int, stroke: Int? = null) = GradientDrawable().apply {
        setColor(color); cornerRadius = r.toFloat(); if (stroke != null) setStroke(dp(1), stroke)
    }
    private fun tv(s: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        text = s; textSize = size; setTextColor(color); setPadding(0, dp(6), 0, dp(6))
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
        textDirection = View.TEXT_DIRECTION_RTL
    }
    private fun TextView.accessibilityHeading() { if (android.os.Build.VERSION.SDK_INT >= 28) isAccessibilityHeading = true }
    private fun bullet(s: String) = tv("• $s", 14f, cText)
    private fun alert(s: String) = tv(s, 14f, danger).apply { accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_ASSERTIVE }
    private fun button(s: String, on: () -> Unit) = Button(this).apply { text = s; minHeight = dp(44); setOnClickListener { on() } }
    private fun section(border: Int? = null) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(12))
        background = round(card, dp(16), border)
        layoutParams = LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) }
    }

    companion object { private const val REQ_SMS = 61 }
}

/** Minimal wrapping row layout for chips (12px gaps), RTL-aware. */
class FlowLayout(context: Context, private val gap: Int) : ViewGroup(context) {
    override fun onMeasure(w: Int, h: Int) {
        val max = MeasureSpec.getSize(w) - paddingLeft - paddingRight
        var x = 0; var y = 0; var rowH = 0
        for (i in 0 until childCount) {
            val c = getChildAt(i)
            c.measure(MeasureSpec.makeMeasureSpec(max, MeasureSpec.AT_MOST), MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED))
            if (x > 0 && x + c.measuredWidth > max) { x = 0; y += rowH + gap; rowH = 0 }
            x += c.measuredWidth + gap; rowH = maxOf(rowH, c.measuredHeight)
        }
        setMeasuredDimension(MeasureSpec.getSize(w), y + rowH + paddingTop + paddingBottom + gap)
    }
    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val max = r - l - paddingLeft - paddingRight
        val rtl = layoutDirection == View.LAYOUT_DIRECTION_RTL
        var x = 0; var y = paddingTop; var rowH = 0
        for (i in 0 until childCount) {
            val c = getChildAt(i)
            if (x > 0 && x + c.measuredWidth > max) { x = 0; y += rowH + gap; rowH = 0 }
            val left = if (rtl) r - l - paddingRight - x - c.measuredWidth else paddingLeft + x
            c.layout(left, y, left + c.measuredWidth, y + c.measuredHeight)
            x += c.measuredWidth + gap; rowH = maxOf(rowH, c.measuredHeight)
        }
    }
}
