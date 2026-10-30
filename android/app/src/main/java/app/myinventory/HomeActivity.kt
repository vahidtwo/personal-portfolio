package app.myinventory

import android.content.Intent
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.CountDownTimer
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.addCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.edit
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import kotlin.concurrent.thread

/**
 * Phase 4 launcher: native login (step a/b) and native home with a 5-item bottom nav. The other tabs open
 * MainActivity (WebView) on the same cookie session. Login and home use FLAG_SECURE.
 */
class HomeActivity : AppCompatActivity() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var root: FrameLayout
    private lateinit var scroll: ScrollView
    private lateinit var content: LinearLayout
    private lateinit var nav: LinearLayout
    private lateinit var c: Palette
    private lateinit var cache: HomeCache
    private var regular: Typeface? = null
    private var bold: Typeface? = null
    private var createdAt = 0L
    private var screen = Screen.LOGIN
    private var step = "a"
    private var typedUsername = ""
    private var lock: CountDownTimer? = null
    private var busy = false
    private var lastHome: JSONObject? = null
    private var lastSavedAt = 0L
    private var homeLoadedOnline = false

    enum class Screen { LOGIN, HOME }


    data class Palette(
        val bg: Int, val surface: Int, val surface2: Int, val text: Int, val muted: Int,
        val accent: Int, val onAccent: Int, val danger: Int, val warn: Int, val dark: Boolean,
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        createdAt = SystemClock.uptimeMillis()
        installSplashScreen()
        super.onCreate(savedInstanceState)
        if (BuildConfig.SECURE_SCREENS) window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.TRANSPARENT
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        val dark = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
        c = if (dark) Palette(0xFF050608.toInt(), 0xFF11141C.toInt(), 0xFF1B2030.toInt(), 0xFFF4F6FB.toInt(),
            0xFFA3ABBD.toInt(), 0xFF3EE0B8.toInt(), 0xFF04120E.toInt(), 0xFFFF8A7A.toInt(), 0xFFF5B942.toInt(), true)
        else Palette(0xFFEEF1F8.toInt(), 0xFFFFFFFF.toInt(), 0xFFE6EAF3.toInt(), 0xFF0B1220.toInt(),
            0xFF4F5869.toInt(), 0xFF08735A.toInt(), 0xFFFFFFFF.toInt(), 0xFFB42318.toInt(), 0xFF8A4A05.toInt(), false)
        regular = runCatching { resources.getFont(R.font.vazirmatn) }.getOrNull()
        bold = runCatching { resources.getFont(R.font.vazirmatn_bold) }.getOrNull()
        cache = HomeCache(this)
        getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).edit { putString(MainActivity.KEY_URL, NativeSession.BASE) }

        root = FrameLayout(this).apply { setBackgroundColor(c.bg); layoutDirection = View.LAYOUT_DIRECTION_RTL }
        scroll = ScrollView(this).apply { isFillViewport = true }
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(24)) }
        scroll.addView(content)
        nav = buildNav()
        root.addView(scroll, FrameLayout.LayoutParams(-1, -1))
        root.addView(nav, FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { _, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            nav.setPadding(0, dp(4), 0, bars.bottom)
            val bottom = if (screen == Screen.HOME) nav.height.coerceAtLeast(dp(72)) + bars.bottom else maxOf(ime.bottom, bars.bottom)
            scroll.setPadding(0, bars.top, 0, bottom)
            insets
        }

        onBackPressedDispatcher.addCallback(this) {
            if (screen == Screen.LOGIN && step == "b") {
                step = "a"; showLogin()
            } else {
                isEnabled = false; onBackPressedDispatcher.onBackPressed()
            }
        }

        if (NativeSession.signedIn()) showHome() else showLogin()
        Log.i(StartupGate.TAG, "native ${screen.name.lowercase()} +${SystemClock.uptimeMillis() - createdAt}ms")
    }

    override fun onResume() {
        super.onResume()
        // A web logout (settings tab) clears the shared cookies: drop the native copy too.
        if (screen == Screen.HOME && !NativeSession.signedIn()) signOutLocal()
    }

    override fun onDestroy() {
        lock?.cancel()
        super.onDestroy()
    }

    // ---------- small view helpers ----------
    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun text(s: String, size: Float = 15f, color: Int = c.text, isBold: Boolean = false): TextView =
        TextView(this).apply {
            text = s; setTextColor(color); setTextSize(TypedValue.COMPLEX_UNIT_SP, size)
            typeface = if (isBold) bold else regular
            textDirection = View.TEXT_DIRECTION_ANY_RTL
        }

    private fun bg(color: Int, radius: Int = 16, stroke: Int = 0): GradientDrawable = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(radius).toFloat(); if (stroke != 0) setStroke(dp(1), stroke)
    }

    private fun lp(top: Int = 0): LinearLayout.LayoutParams =
        LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(top) }

    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; background = bg(c.surface); setPadding(dp(16), dp(14), dp(16), dp(14))
    }

    private fun primary(label: String): Button = Button(this).apply {
        text = label; isAllCaps = false; setTextColor(c.onAccent); typeface = bold
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f); background = bg(c.accent, 12); minHeight = dp(52)
        stateListAnimator = null
    }

    private fun ghost(label: String): Button = Button(this).apply {
        text = label; isAllCaps = false; setTextColor(c.accent); typeface = bold
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f); background = bg(Color.TRANSPARENT, 12, c.accent); minHeight = dp(48)
        stateListAnimator = null
    }

    private fun alert(title: String, sub: String, kind: String): LinearLayout {
        val col = if (kind == "warn") c.warn else c.danger
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = bg(c.surface, 12, col); setPadding(dp(14), dp(12), dp(14), dp(12))
            accessibilityLiveRegion = View.ACCESSIBILITY_LIVE_REGION_ASSERTIVE
            isFocusable = true
            addView(text(title, 15f, col, true))
            if (sub.isNotEmpty()) addView(text(sub, 14f, c.text), lp(4))
        }
    }

    private fun field(label: String, hint: String, password: Boolean, autofill: String): Pair<LinearLayout, EditText> {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        box.addView(text(label, 14f, c.text, true))
        val row = FrameLayout(this)
        val edit = EditText(this).apply {
            setTextColor(c.text); setHintTextColor(c.muted); typeface = regular
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f); background = bg(c.surface, 12, c.muted)
            setPadding(if (password) dp(56) else dp(14), 0, dp(14), 0); minHeight = dp(52)
            textDirection = View.TEXT_DIRECTION_LTR; layoutDirection = View.LAYOUT_DIRECTION_LTR
            gravity = Gravity.CENTER_VERTICAL or Gravity.START
            inputType = if (password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            setAutofillHints(autofill)
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_YES
            contentDescription = label
        }
        row.addView(edit, FrameLayout.LayoutParams(-1, dp(52)))
        if (password) {
            val toggle = text("نمایش", 13f, c.accent, true).apply {
                gravity = Gravity.CENTER; minWidth = dp(48); minHeight = dp(48)
                contentDescription = "نمایش رمز"
                setOnClickListener {
                    val hidden = edit.inputType and InputType.TYPE_TEXT_VARIATION_PASSWORD == InputType.TYPE_TEXT_VARIATION_PASSWORD
                    edit.inputType = InputType.TYPE_CLASS_TEXT or
                        if (hidden) InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD else InputType.TYPE_TEXT_VARIATION_PASSWORD
                    edit.typeface = regular; edit.setSelection(edit.text.length)
                    text = if (hidden) "پنهان" else "نمایش"
                    contentDescription = if (hidden) "پنهان کردن رمز" else "نمایش رمز"
                }
            }
            row.addView(toggle, FrameLayout.LayoutParams(dp(56), dp(52), Gravity.END or Gravity.CENTER_VERTICAL))
        }
        box.addView(row, lp(6))
        val help = text(hint, 13f, c.muted)
        help.tag = "help"
        box.addView(help, lp(4))
        return box to edit
    }

    private fun logo(): ImageView = ImageView(this).apply {
        setImageResource(R.drawable.ic_launcher_foreground)
        contentDescription = "دارایی‌تو"
        background = bg(c.accent, 10)
    }

    // ---------- login ----------
    private fun showLogin(error: JSONObject? = null, offline: Boolean = false) {
        screen = Screen.LOGIN
        nav.visibility = View.GONE
        content.removeAllViews()
        lock?.cancel()
        val top = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        top.addView(logo(), LinearLayout.LayoutParams(dp(28), dp(28)))
        top.addView(text("دارایی‌تو", 17f, c.text, true).apply { setPadding(dp(8), 0, dp(8), 0) })
        content.addView(top, lp(8))
        if (offline) { showOffline(); return }
        if (step == "b") { showStepB(error); return }

        content.addView(text("ورود یا ساخت حساب", 24f, c.text, true).apply { isFocusable = true }, lp(28))
        content.addView(text("اگر حساب دارید وارد می‌شوید. اگر ندارید، در قدم بعد یکی می‌سازیم.", 15f, c.muted), lp(6))
        val result = error?.optString("result").orEmpty()
        var alertView: View? = null
        if (result == "wrong" || result == "locked" || result == "expired" || result == "taken") {
            alertView = alert(error!!.optString("message"), error.optString("sub"), if (result == "locked") "warn" else "danger")
            content.addView(alertView, lp(16))
        }
        val (uBox, user) = field("نام کاربری", "۳ تا ۳۲ حرف انگلیسی یا عدد، بدون فاصله", false, View.AUTOFILL_HINT_USERNAME)
        val (pBox, pass) = field("رمز", "دست‌کم ۸ حرف", true, View.AUTOFILL_HINT_PASSWORD)
        user.setText(typedUsername)
        user.imeOptions = EditorInfo.IME_ACTION_NEXT
        pass.imeOptions = EditorInfo.IME_ACTION_DONE
        content.addView(uBox, lp(18))
        content.addView(pBox, lp(14))
        val uHelp = uBox.findViewWithTag<TextView>("help")
        val pHelp = pBox.findViewWithTag<TextView>("help")
        when (result) {
            "badname" -> { uHelp.text = error!!.optString("message"); uHelp.setTextColor(c.danger); user.background = bg(c.surface, 12, c.danger) }
            "shortpw" -> { pHelp.text = error!!.optString("message"); pHelp.setTextColor(c.danger); pass.background = bg(c.surface, 12, c.danger) }
            "wrong" -> pass.background = bg(c.surface, 12, c.danger)
        }
        val warn = text("صفحه‌کلید فارسی است. رمز را با صفحه‌کلید انگلیسی بنویسید.", 13f, c.warn).apply { visibility = View.GONE }
        content.addView(warn, lp(4))
        pass.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, d: Int) = Unit
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, d: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                warn.visibility = if (Fa.hasPersianLetter(s?.toString().orEmpty())) View.VISIBLE else View.GONE
            }
        })
        val submit = primary("ادامه")
        content.addView(submit, lp(20))
        val spinner = ProgressBar(this).apply { visibility = View.GONE }
        content.addView(spinner, LinearLayout.LayoutParams(dp(28), dp(28)).apply { gravity = Gravity.CENTER_HORIZONTAL; topMargin = dp(8) })
        content.addView(text("رمزتان را فراموش کردید؟ مدیر سایت می‌تواند آن را بازنشانی کند.", 13f, c.muted), lp(18))

        val go = {
            if (!busy && submit.isEnabled) {
                typedUsername = user.text.toString()
                busy = true
                submit.text = "در حال بررسی…"; submit.isEnabled = false
                user.isEnabled = false; pass.isEnabled = false; spinner.visibility = View.VISIBLE
                ViewCompat.setStateDescription(submit, "در حال بررسی")
                val body = JSONObject().put("username", typedUsername).put("password", pass.text.toString())
                thread { val r = call { NativeSession.post("/api/auth/continue", body) }; main.post { busy = false; onAuth(r) } }
            }
        }
        submit.setOnClickListener { go() }
        // One Enter on the username can reach the password field as a second action (key UP or
        // an IME action); ignore password actions for a moment after moving focus there.
        var movedAt = 0L
        val next = { movedAt = SystemClock.uptimeMillis(); pass.requestFocus() }
        user.setOnEditorActionListener { _, id, ev ->
            when {
                ev != null && ev.keyCode == KeyEvent.KEYCODE_ENTER -> { if (ev.action == KeyEvent.ACTION_DOWN) next(); true }
                id == EditorInfo.IME_ACTION_NEXT -> { next(); true }
                else -> false
            }
        }
        pass.setOnEditorActionListener { _, id, ev ->
            val fresh = SystemClock.uptimeMillis() - movedAt < 400
            when {
                ev != null && ev.keyCode == KeyEvent.KEYCODE_ENTER -> { if (ev.action == KeyEvent.ACTION_DOWN && !fresh) go(); true }
                id == EditorInfo.IME_ACTION_DONE -> { if (!fresh) go(); true }
                else -> false
            }
        }
        if (result == "locked") startLock(submit, error!!.optInt("retry_after"))
        when {
            alertView != null -> alertView.post { alertView.requestFocus(); alertView.sendAccessibilityEvent(android.view.accessibility.AccessibilityEvent.TYPE_VIEW_FOCUSED) }
            result == "badname" || typedUsername.isEmpty() -> user.requestFocus()
            else -> pass.requestFocus()
        }
        if (result == "wrong") pass.post { pass.requestFocus() }
    }

    private fun startLock(button: Button, seconds: Int) {
        button.isEnabled = false
        button.alpha = 0.6f
        button.text = Fa.lockedButton(seconds)
        lock = object : CountDownTimer(seconds * 1000L, 1000L) {
            override fun onTick(left: Long) { button.text = Fa.lockedButton((left / 1000).toInt()) }
            override fun onFinish() { button.isEnabled = true; button.alpha = 1f; button.text = "ادامه" }
        }.start()
    }

    private fun showStepB(error: JSONObject?) {
        content.addView(text("حساب تازه بسازیم؟", 24f, c.text, true), lp(28))
        content.addView(text("حسابی با نام $typedUsername نداریم. اگر اشتباه تایپی است، «تغییر» را بزنید. اگر نه، رمز را یک بار دیگر بنویسید.", 15f, c.muted), lp(6))
        val result = error?.optString("result").orEmpty()
        if (result == "mismatch" || result == "signuplimit") {
            content.addView(alert(error!!.optString("message"), error.optString("sub"), if (result == "signuplimit") "warn" else "danger"), lp(16))
        }
        val (cBox, confirm) = field("تکرار رمز عبور", "همان رمزی که در قدم قبل نوشتید", true, View.AUTOFILL_HINT_PASSWORD)
        confirm.setAutofillHints("newPassword")
        confirm.imeOptions = EditorInfo.IME_ACTION_DONE
        content.addView(cBox, lp(18))
        val create = primary("ساخت حساب")
        content.addView(create, lp(20))
        val back = ghost("برگشت")
        content.addView(back, lp(10))
        back.setOnClickListener { step = "a"; showLogin() }
        val go = {
            if (!busy) {
                busy = true; create.isEnabled = false; create.text = "در حال بررسی…"
                val body = JSONObject().put("password_confirm", confirm.text.toString())
                thread { val r = call { NativeSession.post("/api/auth/create", body) }; main.post { busy = false; onAuth(r) } }
            }
        }
        create.setOnClickListener { go() }
        confirm.setOnEditorActionListener { _, id, _ -> if (id == EditorInfo.IME_ACTION_DONE) { go(); true } else false }
        if (result == "signuplimit") startLock(create, error!!.optInt("retry_after"))
        confirm.requestFocus()
    }

    private fun showOffline() {
        content.addView(text("اتصال برقرار نشد", 24f, c.text, true), lp(28))
        val a = alert("اتصال به سرور برقرار نشد.", "اینترنت گوشی را بررسی کنید.", "danger")
        content.addView(a, lp(16))
        content.addView(text("نشانی سرور: daraiito.ir", 13f, c.muted).apply { textDirection = View.TEXT_DIRECTION_RTL }, lp(10))
        val retry = primary("تلاش دوباره")
        content.addView(retry, lp(20))
        content.addView(text("چیزی که نوشته بودید سر جایش می‌ماند.", 13f, c.muted), lp(10))
        retry.setOnClickListener {
            retry.isEnabled = false
            thread {
                val ok = call { NativeSession.request("GET", "/health") }?.status == 200
                main.post { if (ok) showLogin() else { retry.isEnabled = true } }
            }
        }
        a.post { a.requestFocus() }
    }

    private fun <T> call(block: () -> T): T? = try { block() } catch (e: IOException) { null }

    private fun onAuth(r: NativeSession.Response?) {
        if (r == null) { showLogin(offline = true); return }
        val res = r.json
        when (res.optString("result")) {
            "ok" -> { step = "a"; showHome() }
            "stepb" -> { step = "b"; showLogin() }
            "expired", "taken" -> { step = "a"; typedUsername = res.optString("username", typedUsername); showLogin(res) }
            "" -> showLogin(offline = true)
            else -> showLogin(res)
        }
    }

    // ---------- home ----------
    private fun cacheKey(): String? = HomeCache.key(BuildConfig.VERSION_CODE, NativeSession.cookie(NativeSession.PAGE_KEY))

    private fun showHome() {
        screen = Screen.HOME
        nav.visibility = View.VISIBLE
        root.requestApplyInsets()
        val cached = cache.read(cacheKey())
        if (cached != null) {
            lastHome = cached.first; lastSavedAt = cached.second
            renderHome(cached.first, cached.second, fromCache = true)
        } else {
            content.removeAllViews()
            main.postDelayed({ if (screen == Screen.HOME && lastHome == null) renderSkeleton() }, 1000)
        }
        fetchHome()
        // Creating a WebView blocks the main thread for a few hundred ms: wait until the home
        // frame is up so the prewarm never delays it.
        main.postDelayed({ if (screen == Screen.HOME && !isFinishing) WebPrewarm.start(this) }, PREWARM_DELAY_MS)
    }

    private fun fetchHome() {
        thread {
            val r = call { NativeSession.request("GET", "/api/home") }
            main.post {
                if (screen != Screen.HOME) return@post
                when {
                    r == null -> if (lastHome == null) renderHomeError() else renderHome(lastHome!!, lastSavedAt, fromCache = true, offline = true)
                    r.status == 401 -> signOutLocal()
                    r.status == 200 -> {
                        val now = System.currentTimeMillis()
                        cache.write(cacheKey(), r.json, now)
                        lastHome = r.json; lastSavedAt = now; homeLoadedOnline = true
                        renderHome(r.json, now, fromCache = false)
                        Log.i(StartupGate.TAG, "native home fresh +${SystemClock.uptimeMillis() - createdAt}ms")
                    }
                    else -> if (lastHome == null) renderHomeError() else renderHome(lastHome!!, lastSavedAt, fromCache = true, offline = true)
                }
            }
        }
    }

    private fun signOutLocal() {
        cache.clear()
        lastHome = null
        NativeSession.clearLocal()
        WebPrewarm.stop()
        step = "a"
        showLogin()
    }

    private fun masked(): Boolean = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).getBoolean(KEY_MASK, false)

    private fun topBar(withToggle: Boolean): LinearLayout {
        val bar = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; minimumHeight = dp(56) }
        bar.addView(logo(), LinearLayout.LayoutParams(dp(28), dp(28)))
        bar.addView(text("دارایی‌تو", 17f, c.text, true).apply { setPadding(dp(8), 0, dp(8), 0) }, LinearLayout.LayoutParams(0, -2, 1f))
        if (withToggle) {
            val m = masked()
            bar.addView(ghost(if (m) "نمایش" else "پنهان کردن").apply {
                contentDescription = "نمایش یا پنهان کردن خالص دارایی"
                ViewCompat.setStateDescription(this, if (m) "پنهان" else "نمایان")
                setOnClickListener {
                    getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).edit { putBoolean(KEY_MASK, !m) }
                    lastHome?.let { renderHome(it, lastSavedAt, fromCache = !homeLoadedOnline) }
                }
            }, LinearLayout.LayoutParams(-2, dp(48)))
        }
        return bar
    }

    private fun renderSkeleton() {
        content.removeAllViews()
        content.addView(topBar(false))
        content.contentDescription = "در حال بارگذاری"
        for (h in listOf(150, 90, 90, 220)) {
            content.addView(View(this).apply { background = bg(c.surface2) }, LinearLayout.LayoutParams(-1, dp(h)).apply { topMargin = dp(12) })
        }
    }

    private fun renderHomeError() {
        content.removeAllViews()
        content.addView(topBar(false))
        val a = alert("خانه باز نشد.", "اتصال به سرور برقرار نشد. اینترنت را بررسی کنید و دوباره امتحان کنید.", "danger")
        content.addView(a, lp(16))
        content.addView(primary("تلاش دوباره").apply { setOnClickListener { fetchHome() } }, lp(16))
    }

    private fun value(label: String, size: Float, isBold: Boolean = true): TextView {
        val m = masked()
        return text(if (m) "••••••" else label, size, c.text, isBold).apply {
            textDirection = View.TEXT_DIRECTION_RTL
            contentDescription = if (m) "پنهان" else label
        }
    }

    private fun chipView(chip: JSONObject?): TextView {
        val kind = chip?.optString("kind").orEmpty()
        val col = when (kind) { "up" -> c.accent; "down" -> c.danger; else -> c.muted }
        return text(chip?.optString("label") ?: "—", 13f, col, true).apply {
            background = bg(c.surface2, 999); setPadding(dp(10), dp(4), dp(10), dp(4))
        }
    }

    private fun points(arr: JSONArray?): List<Double> = arr?.let { a -> (0 until a.length()).map { a.optDouble(it) } } ?: emptyList()

    private fun renderHome(d: JSONObject, savedAt: Long, fromCache: Boolean, offline: Boolean = false) {
        content.removeAllViews()
        content.contentDescription = null
        content.addView(topBar(!d.optBoolean("empty")))
        if (offline) {
            content.addView(alert("آفلاین هستید.", "آخرین مبلغ‌های ذخیره‌شده، ${Fa.ago(System.currentTimeMillis() - savedAt)}", "warn"), lp(8))
        }
        if (d.optBoolean("empty")) { renderWelcome(); return }
        val m = masked()
        // hero
        val hero = card()
        hero.addView(text("خالص دارایی", 16f, c.text, true))
        hero.addView(text("دارایی منهای بدهی", 13f, c.muted))
        val net = d.optJSONObject("net")?.optJSONObject("big")
        val netRow = LinearLayout(this).apply { gravity = Gravity.BOTTOM }
        netRow.addView(value(net?.optString("label").orEmpty(), 30f))
        netRow.addView(text(" " + (net?.optString("unit") ?: "تومان"), 14f, c.muted))
        hero.addView(netRow, lp(8))
        val chips = LinearLayout(this)
        val changes = d.optJSONArray("changes") ?: JSONArray()
        for (i in 0 until changes.length()) {
            val w = changes.getJSONObject(i)
            chips.addView(text(w.optString("period"), 12f, c.muted).apply { setPadding(0, 0, dp(4), 0) })
            chips.addView(chipView(w), LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(10) })
        }
        hero.addView(chips, lp(10))
        val stats = LinearLayout(this)
        fun stat(title: String, label: String, extra: View? = null) {
            val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            col.addView(text(title, 12f, c.muted))
            col.addView(value(label, 14f))
            extra?.let { col.addView(it, LinearLayout.LayoutParams(dp(64), dp(20))) }
            stats.addView(col, LinearLayout.LayoutParams(0, -2, 1f))
        }
        stat("جمع دارایی", d.optJSONObject("assets_total")?.optString("label").orEmpty())
        stat("جمع بدهی", d.optJSONObject("debt_total")?.optString("label").orEmpty())
        val usd = d.optJSONObject("usd")
        val usdSpark = usd?.optJSONObject("spark")?.takeIf { !m }?.let { s ->
            Sparkline(this, points(s.optJSONArray("points")), if (s.optString("kind") == "down") c.danger else c.accent)
                .apply { contentDescription = s.optString("label") }
        }
        stat("معادل دلاری", usd?.optString("label").orEmpty(), usdSpark)
        hero.addView(stats, lp(14))
        content.addView(hero, lp(8))
        // price line
        val price = d.optJSONObject("price")
        val age = price?.optString("age")?.takeIf { it.isNotEmpty() && it != "null" }
        val priceText = when (price?.optString("state")) {
            "error" -> "قیمت تازه نرسید؛ آخرین قیمت‌ها نشان داده می‌شوند"
            "stale" -> if (age != null) "قیمت‌ها $age پیش به‌روز شد (قدیمی)" else "قیمتی ثبت نشده"
            else -> if (age != null) "قیمت‌ها $age پیش به‌روز شد" else ""
        }
        if (priceText.isNotEmpty()) content.addView(text(priceText, 13f, if (price?.optString("state") == "fresh") c.muted else c.warn), lp(10))
        // tiles
        val tiles = LinearLayout(this)
        fun tile(title: String, main: String, sub: String) {
            val t = card()
            t.addView(text(title, 13f, c.muted, true))
            t.addView(value(main, 15f), lp(4))
            if (sub.isNotEmpty()) t.addView(text(sub, 12f, c.muted), lp(2))
            tiles.addView(t, LinearLayout.LayoutParams(0, -1, 1f).apply { marginStart = dp(4); marginEnd = dp(4) })
        }
        val ni = d.optJSONObject("next_instalment")
        tile("قسط بعدی", ni?.optString("amount_label")?.let { "$it تومان" } ?: "قسطی ثبت نشده", ni?.optString("date_label").orEmpty())
        val ms = d.optJSONObject("month_spend")
        tile("خرج این ماه", "${ms?.optString("month_label")} تومان", "امروز: ${ms?.optString("today_label")} تومان")
        content.addView(tiles, lp(12))
        // assets
        val rows = d.optJSONArray("rows") ?: JSONArray()
        val list = card()
        list.addView(text("دارایی‌ها", 16f, c.text, true))
        list.addView(text("${Fa.digits(rows.length().toString())} مورد، تغییر ۷ روزه", 12f, c.muted))
        for (i in 0 until rows.length()) {
            val r = rows.getJSONObject(i)
            val row = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; minimumHeight = dp(56); setPadding(0, dp(8), 0, dp(8)) }
            val left = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            left.addView(text(r.optString("name_fa"), 15f, c.text, true))
            left.addView(text("${r.optString("quantity_label")} ${r.optString("unit_fa")}", 12f, c.muted))
            row.addView(left, LinearLayout.LayoutParams(0, -2, 1f))
            val spark = r.optJSONObject("spark")
            if (spark != null && !m) {
                val col = runCatching { Color.parseColor(r.optString("color")) }.getOrDefault(c.accent)
                row.addView(Sparkline(this, points(spark.optJSONArray("points")), col).apply { contentDescription = spark.optString("label") },
                    LinearLayout.LayoutParams(dp(72), dp(24)).apply { marginEnd = dp(8) })
            }
            val right = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.END }
            right.addView(value(r.optString("value_label"), 14f))
            val meta = LinearLayout(this)
            meta.addView(text("${r.optString("share_label")}٪ سهم", 12f, c.muted).apply { setPadding(0, 0, dp(6), 0) })
            meta.addView(if (r.optBoolean("has_price")) chipView(r.optJSONObject("chip")) else text("بدون قیمت بازار", 12f, c.muted))
            right.addView(meta)
            row.addView(right)
            list.addView(row)
        }
        content.addView(list, lp(12))
        if (fromCache && !offline) {
            content.addView(text("ذخیره‌شده ${Fa.ago(System.currentTimeMillis() - savedAt)}", 12f, c.muted), lp(8))
        }
    }

    private fun renderWelcome() {
        val w = card()
        w.addView(text("خوش آمدید! بیایید شروع کنیم", 20f, c.text, true))
        w.addView(text("اول دارایی‌هایتان را وارد کنید؛ ارزش امروزشان را همین‌جا با قیمت بازار می‌بینید.", 14f, c.muted), lp(6))
        val steps = listOf(
            "۱" to "دارایی‌ها را وارد کنید\nطلا، سکه، دلار، ارز دیجیتال یا نقد",
            "۲" to "بدهی یا قسط دارید؟\nاختیاری؛ تا خالص دارایی درست حساب شود",
            "۳" to "خرج‌ها خودکار ثبت شوند\nاختیاری؛ با اپ اندروید و پیامک",
        )
        for ((n, t) in steps) {
            val r = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(8), 0, dp(8)) }
            r.addView(text(n, 14f, c.onAccent, true).apply { gravity = Gravity.CENTER; background = bg(c.accent, 999) }, LinearLayout.LayoutParams(dp(28), dp(28)))
            r.addView(text(t, 14f, c.text).apply { setPadding(dp(10), 0, dp(10), 0) })
            w.addView(r)
        }
        w.addView(primary("افزودن دارایی").apply { setOnClickListener { openWeb("/assets") } }, lp(12))
        content.addView(w, lp(8))
    }

    // ---------- bottom nav ----------
    private fun buildNav(): LinearLayout {
        val bar = LinearLayout(this).apply {
            setBackgroundColor(c.surface); visibility = View.GONE; layoutDirection = View.LAYOUT_DIRECTION_RTL
        }
        val items = listOf(
            Triple("خانه", null as String?, "خانه"),
            Triple("دارایی‌ها", "/assets", "دارایی‌ها"),
            Triple("خرج‌ها", "/dashboard?tab=daily", "خرج‌ها"),
            Triple("بدهی‌ها", "/profile?tab=debts", "بدهی‌ها و هزینهٔ ماهانه"),
            Triple("تنظیمات", "/profile", "تنظیمات"),
        )
        for ((label, path, a11y) in items) {
            val active = path == null
            val b = text(label, 12f, if (active) c.accent else c.muted, active).apply {
                gravity = Gravity.CENTER; minHeight = dp(64); contentDescription = a11y
                if (active) { background = bg(c.surface2, 999); isSelected = true }
                setOnClickListener { if (path != null) openWeb(path) }
            }
            bar.addView(b, LinearLayout.LayoutParams(0, dp(64), 1f).apply { setMargins(dp(4), dp(4), dp(4), dp(4)) })
        }
        return bar
    }

    private fun openWeb(path: String) {
        startActivity(Intent(this, MainActivity::class.java).putExtra(MainActivity.EXTRA_PATH, path))
    }

    companion object {
        private const val PREWARM_DELAY_MS = 1500L
        const val KEY_MASK = "native_mask_net"
    }
}
