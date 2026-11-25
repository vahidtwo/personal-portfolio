package app.myinventory

import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import app.myinventory.settings.SettingsData
import app.myinventory.settings.SettingsModel
import app.myinventory.settings.WriteResult
import app.myinventory.ui.components.AlertBox
import app.myinventory.ui.components.AlertKind
import app.myinventory.ui.components.AmountField
import app.myinventory.ui.components.AmountText
import app.myinventory.ui.components.AppCard
import app.myinventory.ui.components.ButtonPair
import app.myinventory.ui.components.AppIcons
import app.myinventory.ui.components.BottomNav
import app.myinventory.ui.components.DangerButton
import app.myinventory.ui.components.LabeledField
import app.myinventory.ui.components.LetterAvatar
import app.myinventory.ui.components.ListCard
import app.myinventory.ui.components.PrimaryButton
import app.myinventory.ui.components.SecondaryButton
import app.myinventory.ui.components.SectionLabel
import app.myinventory.ui.components.SettingsListItem
import app.myinventory.ui.components.SkeletonBlock
import app.myinventory.ui.components.ThemeOption
import app.myinventory.ui.components.ThemeRadioCards
import app.myinventory.ui.components.TopBar
import app.myinventory.ui.format.MASK
import app.myinventory.ui.format.faDigits
import app.myinventory.ui.theme.DaraiitoTheme
import app.myinventory.ui.theme.SheetScrim
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Native «تنظیمات» tab: account, appearance, salary, password and logout.
 * The salary is shown only after «نمایش», kept in screen state only, and dropped when the screen stops.
 * It is never cached, saved to preferences or logged.
 */
class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent { DaraiitoTheme { SettingsRoot() } }
    }

    private sealed interface Load {
        data object Loading : Load
        data object Error : Load
        data class Ready(val data: SettingsData) : Load
    }

    private enum class Page { MAIN, ACCOUNT, PASSWORD, SALARY }

    @Composable
    private fun SettingsRoot() {
        var page by rememberSaveable { mutableStateOf(Page.MAIN) }
        var load by remember { mutableStateOf<Load>(Load.Loading) }
        var attempt by remember { mutableIntStateOf(0) }
        var showSkeleton by remember { mutableStateOf(false) }

        LaunchedEffect(attempt) {
            load = Load.Loading
            showSkeleton = false
            val job = launch { delay(1000); showSkeleton = true }
            val r = withContext(Dispatchers.IO) { runCatching { NativeSession.request("GET", "/api/settings") }.getOrNull() }
            job.cancel()
            load = when {
                r == null -> Load.Error
                r.status == 401 -> { goToLogin(); Load.Error }
                r.status == 200 -> SettingsModel.parse(r.json)?.let { Load.Ready(it) } ?: Load.Error
                else -> Load.Error
            }
        }

        BackHandler(enabled = page != Page.MAIN) { page = Page.MAIN }

        Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            when (page) {
                Page.MAIN -> MainPage(load, showSkeleton, onRetry = { attempt++ }, onOpen = { page = it })
                Page.ACCOUNT, Page.PASSWORD -> (load as? Load.Ready)?.let { ready ->
                    AccountPage(ready.data, toPassword = page == Page.PASSWORD, onSaved = { load = Load.Ready(it) },
                        onBack = { page = Page.MAIN })
                }
                Page.SALARY -> SalaryPage(onBack = { page = Page.MAIN })
            }
        }
    }

    // ---------- main list ----------

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun MainPage(load: Load, showSkeleton: Boolean, onRetry: () -> Unit, onOpen: (Page) -> Unit) {
        var confirmLogout by remember { mutableStateOf(false) }
        var loggingOut by remember { mutableStateOf(false) }
        var theme by remember { mutableStateOf(AppTheme.current(this)) }
        var resumeTick by remember { mutableIntStateOf(0) }
        LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { resumeTick++ }
        val scope = rememberCoroutineScope()

        Column(Modifier.fillMaxSize()) {
            Column(
                Modifier.weight(1f).statusBarsPadding().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            ) {
                TopBar("تنظیمات")
                when (load) {
                    Load.Loading -> if (showSkeleton) SkeletonList()
                    Load.Error -> {
                        AlertBox(AlertKind.Error, "تنظیمات باز نشد.", "اتصال را بررسی کنید و دوباره امتحان کنید.")
                        Spacer(Modifier.height(12.dp))
                        PrimaryButton("دوباره", onRetry, Modifier.fillMaxWidth(), icon = AppIcons.Refresh)
                    }
                    is Load.Ready -> {
                        val d = load.data
                        AppCard(padding = 14.dp) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                LetterAvatar(SettingsModel.avatarLetter(d.fullName, d.username))
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(d.fullName.ifEmpty { d.username }, style = MaterialTheme.typography.titleSmall,
                                        color = MaterialTheme.colorScheme.onSurface)
                                    Text(d.username, style = MaterialTheme.typography.bodySmall.copy(textDirection = TextDirection.Ltr),
                                        color = DaraiitoTheme.extended.textMuted)
                                }
                                TextButton(onClick = { onOpen(Page.ACCOUNT) }) {
                                    Text("حساب", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                                }
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        AppCard {
                            Text("ظاهر", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurface)
                            Spacer(Modifier.height(12.dp))
                            ThemeRadioCards(
                                listOf(
                                    ThemeOption(AppTheme.AUTO, "خودکار", "مثل دستگاه"),
                                    ThemeOption(AppTheme.DARK, "تیره"),
                                    ThemeOption(AppTheme.LIGHT, "روشن"),
                                ),
                                theme,
                            ) { theme = it; AppTheme.set(this@SettingsActivity, it) }
                        }
                        SectionLabel("حساب و پول")
                        val smsActive = remember(resumeTick) { SmsPrefs.isActive(this@SettingsActivity) }
                        val smsWords = remember(resumeTick) { SmsPrefs.keywords(this@SettingsActivity).size }
                        ListCard(listOf(
                            {
                                SettingsListItem(AppIcons.Assets, "حقوق ماهانه", "همیشه پنهان؛ برای «مانده»",
                                    trailing = MASK) { onOpen(Page.SALARY) }
                            },
                            {
                                SettingsListItem(AppIcons.Bell, "اعلان‌ها", "در صفحهٔ وب باز می‌شود") { openWeb(WEB_PUSH) }
                            },
                            {
                                SettingsListItem(AppIcons.Message, "ثبت خودکار خرج از پیامک", "فقط روی همین گوشی",
                                    trailing = SettingsModel.smsTrailing(smsActive, smsWords, ::faDigits)) {
                                    startActivity(Intent(this@SettingsActivity, SmsSettingsActivity::class.java))
                                }
                            },
                        ))
                        SectionLabel("امنیت")
                        ListCard(listOf({ SettingsListItem(AppIcons.Lock, "رمز عبور") { onOpen(Page.PASSWORD) } }))
                        SectionLabel("اپ")
                        val appRows = mutableListOf<@Composable () -> Unit>(
                            { SettingsListItem(AppIcons.Phone, "نسخهٔ اپ", SettingsModel.versionLabel(BuildConfig.VERSION_NAME, ::faDigits), showChevron = false) },
                            { SettingsListItem(AppIcons.Server, "پیشرفته: توکن MCP", "در صفحهٔ وب باز می‌شود") { openWeb(WEB_MCP) } },
                        )
                        if (d.isAdmin) appRows += { SettingsListItem(AppIcons.Shield, "مدیریت", "در صفحهٔ وب باز می‌شود") { openWeb("/admin") } }
                        ListCard(appRows)
                        Spacer(Modifier.height(16.dp))
                        ListCard(listOf({
                            SettingsListItem(AppIcons.Logout, "خروج", showChevron = false, danger = true) { confirmLogout = true }
                        }))
                        Spacer(Modifier.height(24.dp))
                    }
                }
            }
            BottomNav("settings") { key -> onNav(key) }
        }

        if (confirmLogout) {
            val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ModalBottomSheet(
                onDismissRequest = { if (!loggingOut) confirmLogout = false }, sheetState = sheet, scrimColor = SheetScrim,
                containerColor = MaterialTheme.colorScheme.surface,
            ) {
                Column(Modifier.padding(horizontal = 20.dp).navigationBarsPadding().padding(bottom = 16.dp)) {
                    Text("از حساب خارج می‌شوید؟", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface)
                    Spacer(Modifier.height(10.dp))
                    Text("برای ورود دوباره، نام کاربری و رمز لازم است. اعلان‌های این گوشی هم قطع می‌شود.",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(20.dp))
                    // «انصراف» first (right), «خروج» on the left; stacked with large text.
                    ButtonPair({ m -> SecondaryButton("انصراف", { confirmLogout = false }, m, enabled = !loggingOut) }) { m ->
                        DangerButton("خروج", {
                            loggingOut = true
                            scope.launch {
                                withContext(Dispatchers.IO) { logoutRemote() }
                                finishLogout()
                            }
                        }, m, busy = loggingOut)
                    }
                }
            }
        }
    }

    @Composable
    private fun SkeletonList() {
        AppCard { SkeletonBlock(Modifier.fillMaxWidth(.6f), 20.dp); Spacer(Modifier.height(10.dp)); SkeletonBlock(Modifier.fillMaxWidth(.4f)) }
        Spacer(Modifier.height(12.dp))
        AppCard { SkeletonBlock(Modifier.fillMaxWidth(.3f)); Spacer(Modifier.height(12.dp)); SkeletonBlock(Modifier.fillMaxWidth(), 64.dp, 16.dp) }
        Spacer(Modifier.height(12.dp))
        AppCard { repeat(3) { SkeletonBlock(Modifier.fillMaxWidth(), 40.dp, 12.dp); Spacer(Modifier.height(12.dp)) } }
    }

    // ---------- account and password ----------

    @Composable
    private fun AccountPage(data: SettingsData, toPassword: Boolean, onSaved: (SettingsData) -> Unit, onBack: () -> Unit) {
        var name by rememberSaveable { mutableStateOf(data.fullName) }
        var username by rememberSaveable { mutableStateOf(data.username) }
        var mobile by rememberSaveable { mutableStateOf(data.mobile) }
        var accPw by remember { mutableStateOf("") }
        var accBusy by remember { mutableStateOf(false) }
        var accResult by remember { mutableStateOf<WriteResult?>(null) }
        var accOffline by remember { mutableStateOf(false) }
        var current by remember { mutableStateOf("") }
        var fresh by remember { mutableStateOf("") }
        var pwBusy by remember { mutableStateOf(false) }
        var pwResult by remember { mutableStateOf<WriteResult?>(null) }
        var pwOffline by remember { mutableStateOf(false) }
        val scope = rememberCoroutineScope()
        val needPw = SettingsModel.needsCurrentPassword(data.username, username)
        val scroll = rememberScrollState()
        LaunchedEffect(toPassword) { if (toPassword) { delay(50); scroll.animateScrollTo(scroll.maxValue) } }

        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
            TopBar("حساب", onBack)
            Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 16.dp)) {
                AppCard {
                    Text("حساب", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurface)
                    Spacer(Modifier.height(14.dp))
                    val e = accResult?.errors.orEmpty()
                    if (accResult?.ok == true) { AlertBox(AlertKind.Success, accResult!!.title, accResult!!.detail); Spacer(Modifier.height(12.dp)) }
                    if (accResult?.ok == false) {
                        AlertBox(AlertKind.Error, if (e.size == 1) e.values.first() else "ذخیره نشد", if (e.size > 1) e.values.first() else null)
                        Spacer(Modifier.height(12.dp))
                    }
                    if (accOffline) { AlertBox(AlertKind.Error, "ذخیره نشد", "اتصال را بررسی کنید و دوباره بزنید."); Spacer(Modifier.height(12.dp)) }
                    LabeledField("نام", name, { name = it.take(80) })
                    Spacer(Modifier.height(14.dp))
                    LabeledField("نام کاربری", username, { username = it }, hint = "۳ تا ۳۲ حرف انگلیسی یا عدد، بدون فاصله",
                        error = e["username"], ltr = true)
                    Spacer(Modifier.height(14.dp))
                    LabeledField("موبایل", mobile, { mobile = it }, hint = "اختیاری، مثلاً ۰۹۱۲۳۴۵۶۷۸۹", error = e["mobile"],
                        ltr = true, keyboardType = androidx.compose.ui.text.input.KeyboardType.Phone)
                    if (needPw) {
                        Spacer(Modifier.height(14.dp))
                        LabeledField("رمز فعلی", accPw, { accPw = it }, hint = "برای تغییر نام کاربری لازم است.",
                            error = e["current_password"], ltr = true, password = true)
                    }
                    Spacer(Modifier.height(18.dp))
                    PrimaryButton("ذخیرهٔ حساب", {
                        accBusy = true; accOffline = false
                        scope.launch {
                            val body = JSONObject().put("full_name", name).put("username", username).put("mobile", mobile)
                                .put("current_password", if (needPw) accPw else "")
                            val r = withContext(Dispatchers.IO) { write("/api/settings/account", body) }
                            accBusy = false
                            if (r == null) { accOffline = true; accResult = null; return@launch }
                            accResult = r
                            if (r.ok) {
                                accPw = ""
                                val updated = SettingsModel.withAccount(data, r.json)
                                username = updated.username; mobile = updated.mobile; name = updated.fullName
                                onSaved(updated)
                            }
                        }
                    }, Modifier.fillMaxWidth(), busy = accBusy)
                }
                Spacer(Modifier.height(12.dp))
                AppCard {
                    Text("رمز عبور", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurface)
                    Spacer(Modifier.height(14.dp))
                    val e = pwResult?.errors.orEmpty()
                    if (pwResult?.ok == true) { AlertBox(AlertKind.Success, pwResult!!.title, pwResult!!.detail); Spacer(Modifier.height(12.dp)) }
                    if (pwResult?.ok == false) {
                        AlertBox(AlertKind.Error, if (e.size == 1) e.values.first() else "تغییر نکرد", if (e.size > 1) e.values.first() else null)
                        Spacer(Modifier.height(12.dp))
                    }
                    if (pwOffline) { AlertBox(AlertKind.Error, "تغییر نکرد", "اتصال را بررسی کنید و دوباره بزنید."); Spacer(Modifier.height(12.dp)) }
                    LabeledField("رمز فعلی", current, { current = it }, error = e["current_password"], ltr = true, password = true)
                    Spacer(Modifier.height(14.dp))
                    LabeledField("رمز جدید", fresh, { fresh = it }, hint = "دست‌کم ۸ نویسه.", error = e["new_password"], ltr = true, password = true)
                    Spacer(Modifier.height(18.dp))
                    SecondaryButton("تغییر رمز", {
                        pwBusy = true; pwOffline = false
                        scope.launch {
                            val body = JSONObject().put("current_password", current).put("new_password", fresh)
                            val r = withContext(Dispatchers.IO) { write("/api/settings/password", body) }
                            pwBusy = false
                            if (r == null) { pwOffline = true; pwResult = null; return@launch }
                            pwResult = r
                            if (r.ok) { current = ""; fresh = "" }
                        }
                    }, Modifier.fillMaxWidth(), busy = pwBusy)
                }
                Spacer(Modifier.height(24.dp))
            }
        }
    }

    // ---------- salary ----------

    @Composable
    private fun SalaryPage(onBack: () -> Unit) {
        // Plain remember only: never saved state, never preferences, never the home cache. The list and the
        // settings API never say whether a salary exists; only a tap on «نمایش» asks the server.
        var shown by remember { mutableStateOf<Pair<String, String>?>(null) }
        var none by remember { mutableStateOf(false) }
        var revealBusy by remember { mutableStateOf(false) }
        var revealFailed by remember { mutableStateOf(false) }
        var editing by remember { mutableStateOf(false) }
        var input by remember { mutableStateOf("") }
        var saveBusy by remember { mutableStateOf(false) }
        var saveError by remember { mutableStateOf<String?>(null) }
        var saved by remember { mutableStateOf<WriteResult?>(null) }
        val scope = rememberCoroutineScope()

        LifecycleEventEffect(Lifecycle.Event.ON_STOP) {
            shown = null; none = false; revealBusy = false; input = ""
        }
        // Keep a revealed salary out of the recents thumbnail while screenshots stay allowed.
        DisposableEffect(shown != null) {
            if (Build.VERSION.SDK_INT >= 33) setRecentsScreenshotEnabled(shown == null)
            onDispose { if (Build.VERSION.SDK_INT >= 33) setRecentsScreenshotEnabled(true) }
        }

        fun reveal() {
            revealBusy = true; revealFailed = false
            scope.launch {
                val r = withContext(Dispatchers.IO) { runCatching { NativeSession.request("GET", "/api/salary") }.getOrNull() }
                revealBusy = false
                if (r?.status == 401) { goToLogin(); return@launch }
                val parts = if (r?.status == 200) SettingsModel.salaryParts(r.json.optString("salary")) else null
                when {
                    parts == null -> revealFailed = true
                    SettingsModel.salaryIsNone(parts.first) -> { none = true; editing = true }
                    else -> shown = parts
                }
            }
        }

        Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding().imePadding()) {
            TopBar("حقوق ماهانه", onBack)
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp)) {
                AppCard {
                    Text("فقط برای حساب «مانده» در گزارش ماهانه. همیشه پنهان است تا خودتان نمایشش دهید.",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(16.dp))
                    saved?.let { AlertBox(AlertKind.Success, it.title, it.detail); Spacer(Modifier.height(12.dp)) }
                    if (editing) {
                        if (none) {
                            Text("هنوز حقوقی ثبت نکرده‌اید.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
                            Spacer(Modifier.height(12.dp))
                        }
                        AmountField(if (none) "حقوق ماهانه" else "حقوق جدید", input, { input = it; saveError = null },
                            hint = if (none) null else "مبلغ فعلی اینجا نمایش داده نمی‌شود.", error = saveError)
                        Spacer(Modifier.height(16.dp))
                        ButtonPair(
                            if (none) null else { m -> SecondaryButton("انصراف", { editing = false; input = ""; saveError = null }, m) },
                        ) { m ->
                            PrimaryButton("ذخیرهٔ حقوق", {
                                if (input.isEmpty()) { saveError = SALARY_EMPTY; return@PrimaryButton }
                                saveBusy = true; saveError = null
                                scope.launch {
                                    val r = withContext(Dispatchers.IO) {
                                        write("/api/settings/salary", JSONObject().put("salary_toman", input))
                                    }
                                    saveBusy = false
                                    when {
                                        r == null -> saveError = "ذخیره نشد. اتصال را بررسی کنید و دوباره بزنید."
                                        r.ok -> { input = ""; shown = null; none = false; editing = false; saved = r }
                                        else -> saveError = r.errors["salary_toman"] ?: "ذخیره نشد."
                                    }
                                }
                            }, m, busy = saveBusy)
                        }
                    } else {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("حقوق فعلی", style = MaterialTheme.typography.bodySmall, color = DaraiitoTheme.extended.textMuted)
                                Row(Modifier.semantics(mergeDescendants = true) {
                                    if (shown == null) contentDescription = "حقوق فعلی پنهان"
                                }) {
                                    AmountText(shown?.first ?: MASK, DaraiitoTheme.amount.large,
                                        Modifier.weight(1f, fill = false).alignByBaseline(),
                                        maxSize = 24.sp, minSize = 15.sp, color = MaterialTheme.colorScheme.onSurface)
                                    Spacer(Modifier.width(6.dp))
                                    Text(shown?.second ?: "تومان", style = MaterialTheme.typography.bodyMedium,
                                        color = DaraiitoTheme.extended.textMuted, modifier = Modifier.alignByBaseline())
                                }
                            }
                            Spacer(Modifier.width(12.dp))
                            SecondaryButton(
                                when { revealBusy -> "در حال دریافت…"; shown != null -> "پنهان کردن"; else -> "نمایش" },
                                { if (shown != null) shown = null else reveal() },
                                modifier = Modifier.semantics { stateDescription = if (shown != null) "نمایان" else "پنهان" },
                                icon = if (shown != null) AppIcons.EyeOff else AppIcons.Eye, busy = revealBusy,
                                busyLabel = revealBusy, accent = shown != null,
                            )
                        }
                        if (shown != null) {
                            Spacer(Modifier.height(8.dp))
                            Text("با ترک این صفحه دوباره پنهان می‌شود.", style = MaterialTheme.typography.bodySmall,
                                color = DaraiitoTheme.extended.textMuted)
                        }
                        if (revealFailed) {
                            Spacer(Modifier.height(10.dp))
                            AlertBox(AlertKind.Error, "نمایش نشد. اتصال را بررسی کنید و دوباره بزنید.")
                        }
                        Spacer(Modifier.height(16.dp))
                        SecondaryButton("تغییر", { editing = true; saved = null; shown = null }, Modifier.fillMaxWidth(), icon = AppIcons.Edit)
                    }
                }
            }
        }
    }

    // ---------- actions ----------

    /** Settings writes use POST (HttpURLConnection has no PATCH); the server accepts both. */
    private fun write(path: String, body: JSONObject): WriteResult? {
        val r = runCatching { NativeSession.post(path, body) }.getOrNull() ?: return null
        if (r.status == 401) { runOnUiThread { goToLogin() }; return null }
        // 429: too many wrong current passwords; the body carries the message for that field.
        if (r.status != 200 && r.status != 422 && r.status != 429) return null
        return SettingsModel.writeResult(r.status, r.json)
    }

    /** Stop this phone's notifications first, then end the session. Each step is best effort. */
    private fun logoutRemote() {
        PushRegistrar.registeredToken(this)?.let { token ->
            runCatching { NativeSession.request("POST", "/api/push/unregister", JSONObject().put("token", token)) }
        }
        PushRegistrar.forgetRegistration(this)
        runCatching { NativeSession.post("/api/auth/logout", JSONObject()) }
    }

    private fun finishLogout() {
        HomeCache(this).clear()
        NativeSession.clearLocal()
        WebPrewarm.stop()
        goToLogin()
    }

    private fun goToLogin() {
        if (isFinishing) return
        startActivity(Intent(this, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK or Intent.FLAG_ACTIVITY_NEW_TASK))
        finish()
    }

    private fun onNav(key: String) {
        when (key) {
            "settings" -> Unit
            "home" -> {
                startActivity(Intent(this, HomeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
                finish()
            }
            else -> WebNav.ITEMS.firstOrNull { it.key == key }?.let { openWeb(it.href); finish() }
        }
    }

    private fun openWeb(path: String) {
        startActivity(Intent(this, MainActivity::class.java).putExtra(MainActivity.EXTRA_PATH, path))
    }

    companion object {
        const val WEB_PUSH = "/profile#push-settings"
        const val SALARY_EMPTY = "مبلغ را بدون ممیز بنویسید؛ مثلاً ۲٬۵۰۰٬۰۰۰"
        const val WEB_MCP = "/profile#advanced"
    }
}
