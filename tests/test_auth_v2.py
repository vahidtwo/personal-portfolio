"""/auth v2 (spec /workspace/mockups/app-v2/login/spec.md): lockout minutes + Retry-After, inline field errors,
generic wrong-credentials alert, expired sign-up refill, sign-up limit, theme, Persian-keyboard hint, admin-only reset.
FAKE users only; no network; no migration."""
import re

from app import rate_limit
from tests.test_unified_auth import _continue, _csrf, _signup


def _logout(client):
    client.post("/logout", data={"csrf": _csrf(client, "/dashboard")})


def _users():
    from app.db import SessionLocal  # the client fixture reloads app modules per test
    from app.models import User

    db = SessionLocal()
    try:
        return [u.username for u in db.query(User).order_by(User.id).all()]
    finally:
        db.close()


def _locked_client(client, fails=None):
    assert _signup(client, "lockme").status_code == 303
    _logout(client)
    for _ in range(fails or rate_limit.LOGIN_FAILS_PER_USER):
        _continue(client, "lockme", "wrongpass1")


def test_retry_after_unit(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])
    assert rate_limit.retry_after("k", 3, 900) == 0
    for _ in range(2):
        rate_limit.record("k", 900)
        clock[0] += 10
    assert rate_limit.retry_after("k", 3, 900) == 0  # 2 hits < limit 3
    rate_limit.record("k", 900)  # hits at t=1000, 1010, 1020; now 1020
    assert rate_limit.retry_after("k", 3, 900) == 880  # the oldest leaves at t=1900
    clock[0] += 400
    assert rate_limit.retry_after("k", 3, 900) == 480
    rate_limit.record("k", 900)  # 4 hits, limit 3: it takes the 2nd-oldest to leave to drop below
    assert rate_limit.retry_after("k", 3, 900) == 490
    clock[0] += 10_000
    assert rate_limit.retry_after("k", 3, 900) == 0


def test_lockout_shows_minutes_and_retry_after_header(client, monkeypatch):
    _locked_client(client)
    r = _continue(client, "lockme", "password123")
    assert r.status_code == 429
    assert 880 <= int(r.headers["retry-after"]) <= 900
    assert "چند بار پشت سر هم اشتباه شد." in r.text
    assert "تا حدود <bdi class=\"num\">" not in r.text  # minutes come from the server text, in Persian digits
    assert "تا حدود ۱۵ دقیقهٔ دیگر بسته است." in r.text
    assert 'class="alert warn"' in r.text and 'role="alert"' in r.text and "data-autofocus" in r.text
    btn = re.search(r"<button[^>]*data-retry-seconds[^>]*>.*?</button>", r.text, re.S).group(0)
    assert "disabled" in btn and re.search(r'data-retry-seconds="(88\d|89\d|900)"', btn) and "دوباره امتحان کنید، <bdi>۱۵</bdi> دقیقهٔ دیگر" in btn
    assert 'value="lockme"' in r.text and "password123" not in r.text
    # time passes: 5 minutes later it says 10, and the header counts down
    real = rate_limit.time.monotonic
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: real() + 300)
    later = _continue(client, "lockme", "password123")
    assert later.status_code == 429 and 595 <= int(later.headers["retry-after"]) <= 600
    assert "تا حدود ۱۰ دقیقهٔ دیگر بسته است." in later.text
    # after the window the right password gets in again
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: real() + 901)
    ok = _continue(client, "lockme", "password123")
    assert ok.status_code == 303 and ok.headers["location"] == "/dashboard"


def test_lockout_minutes_round_up(client, monkeypatch):
    _locked_client(client)
    real = rate_limit.time.monotonic
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: real() + 841)  # 59 s left -> still «۱ دقیقه»
    r = _continue(client, "lockme", "password123")
    assert r.status_code == 429 and "تا حدود ۱ دقیقهٔ دیگر" in r.text.replace("۱ دقیقهٔ", "۱ دقیقهٔ")
    assert 1 <= int(r.headers["retry-after"]) <= 60


def test_wrong_password_is_one_generic_alert(client):
    assert _signup(client, "alice1").status_code == 303
    _logout(client)
    r = _continue(client, "alice1", "wrongpass1")
    assert r.status_code == 200 and "Retry-After" not in r.headers
    assert "نام کاربری یا رمز درست نیست." in r.text and "رمز را دوباره بنویسید. حروف بزرگ و کوچک فرق دارند." in r.text
    assert 'role="alert"' in r.text and 'class="alert"' in r.text
    pw = re.search(r'<input[^>]*id="password"[^>]*>', r.text).group(0)
    assert 'aria-invalid="true"' in pw and "autofocus" in pw and "value=" not in pw
    user = re.search(r'<input[^>]*id="username"[^>]*>', r.text).group(0)
    assert 'aria-invalid' not in user and 'value="alice1"' in user and "autofocus" not in user
    assert "wrongpass1" not in r.text
    # a name that is not an account never says "no such user" at step a: it goes to the create step instead
    assert "نداریم" not in r.text


def test_empty_password_is_the_same_generic_alert(client):
    r = _continue(client, "alice1", "")
    assert "نام کاربری یا رمز درست نیست." in r.text and _users() == []


def test_bad_username_is_inline_on_the_username_field(client):
    r = _continue(client, "1x", "password123")
    assert r.status_code == 200 and _users() == []
    assert 'role="alert"' not in r.text
    user = re.search(r'<input[^>]*id="username"[^>]*>', r.text).group(0)
    assert 'aria-invalid="true"' in user and "autofocus" in user
    assert re.search(r'<p class="hint bad" id="username-hint">نام کاربری باید با حرف انگلیسی شروع شود و ۳ تا ۳۲ حرف باشد\.</p>', r.text)
    pw = re.search(r'<input[^>]*id="password"[^>]*>', r.text).group(0)
    assert "aria-invalid" not in pw and "autofocus" not in pw


def test_short_password_for_new_name_is_inline_on_password_and_creates_nothing(client):
    r = _continue(client, "brandnew_x", "short")
    assert r.status_code == 200 and _users() == [] and "حساب تازه بسازیم؟" not in r.text
    assert 'role="alert"' not in r.text
    assert re.search(r'<p class="hint bad" id="password-hint"[^>]*>برای حساب تازه، رمز دست‌کم ۸ حرف باشد\.</p>', r.text)
    pw = re.search(r'<input[^>]*id="password"[^>]*>', r.text).group(0)
    assert 'aria-invalid="true"' in pw and "autofocus" in pw
    assert 'value="brandnew_x"' in r.text


def test_short_password_for_existing_user_is_just_wrong_password(client):
    assert _signup(client, "alice1").status_code == 303
    _logout(client)
    r = _continue(client, "alice1", "short")
    assert "نام کاربری یا رمز درست نیست." in r.text and "برای حساب تازه" not in r.text


def test_nothing_is_created_before_the_confirm_step(client):
    for name, pw in (("brandnew_y", "password123"), ("1x", "password123"), ("brandnew_z", "short")):
        _continue(client, name, pw)
        assert _users() == []
    # step b page itself: the typo guard names the account, the password is never in the page
    r = _continue(client, "brandnew_y", "s3cret-pass-xyz")
    assert _users() == [] and "s3cret-pass-xyz" not in r.text
    assert "حسابی با نام <b class=\"latin\" dir=\"ltr\">brandnew_y</b> نداریم. اگر اشتباه تایپی است، «تغییر» را بزنید." in r.text
    assert "رمز را یک بار دیگر بنویسید." in r.text


def test_mismatch_has_help_line_and_focus_on_confirm(client):
    r = _continue(client, "brandnew_y", "password123")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    bad = client.post("/auth/create", data={"password_confirm": "different1", "csrf": csrf}, follow_redirects=False)
    assert bad.status_code == 200 and _users() == []
    assert "<b>دو رمز یکی نیستند.</b><span>رمز را یک بار دیگر بنویسید، یا برگردید و از اول بنویسید.</span>" in bad.text
    confirm = re.search(r'<input[^>]*id="password_confirm"[^>]*>', bad.text).group(0)
    assert 'aria-invalid="true"' in confirm and "autofocus" in confirm
    assert 'class="hint bad"' in bad.text


def test_expired_signup_refills_username_only(client, monkeypatch):
    import app.unified_auth as ua
    r = _continue(client, "brandnew_y", "password123")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    monkeypatch.setattr(ua, "_now", lambda: 10**12)
    late = client.post("/auth/create", data={"password_confirm": "password123", "csrf": csrf}, follow_redirects=False)
    assert late.status_code == 200 and _users() == []
    assert "<b>زمان ساخت حساب تمام شد.</b><span>برای امنیت، نام کاربری و رمز را دوباره بنویسید.</span>" in late.text
    user = re.search(r'<input[^>]*id="username"[^>]*>', late.text).group(0)
    assert 'value="brandnew_y"' in user and "autofocus" in user
    assert "password123" not in late.text
    # a second stale post has nothing left to refill
    again = client.post("/auth/create", data={"password_confirm": "password123", "csrf": csrf}, follow_redirects=False)
    assert "زمان ساخت حساب تمام شد." in again.text and 'value=""' in again.text


def test_signup_limit_shows_minutes_header_and_keeps_back_link(client):
    r = _continue(client, "brandnew_y", "password123")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    from app import rate_limit  # live module: the client fixture reloads app modules per test

    for _ in range(rate_limit.REGISTER_PER_IP):
        rate_limit.record("register:ip:testclient", rate_limit.REGISTER_WINDOW_SECONDS)
    lim = client.post("/auth/create", data={"password_confirm": "password123", "csrf": csrf}, follow_redirects=False)
    assert lim.status_code == 429 and 3580 <= int(lim.headers["retry-after"]) <= 3600
    assert "از این شبکه حساب زیادی ساخته شده." in lim.text
    assert "حدود ۶۰ دقیقهٔ دیگر دوباره امتحان کنید. اگر حساب دارید، نام کاربری را بررسی کنید." in lim.text
    btn = re.search(r"<button[^>]*data-retry-seconds[^>]*>.*?</button>", lim.text, re.S).group(0)
    assert "disabled" in btn and "ساخت حساب، <bdi>۶۰</bdi> دقیقهٔ دیگر" in btn
    assert 'class="alert warn"' in lim.text and 'href="/auth?back=1"' in lim.text
    assert _users() == []


def test_theme_follows_device_key_and_title_separator(client):
    page = client.get("/auth").text
    assert 'localStorage.getItem("inventory-theme")' in page and "prefers-color-scheme: light" in page
    assert "<title>ورود یا ساخت حساب، دارایی‌تو</title>" in page and "·" not in re.search(r"<title>.*?</title>", page).group(0)
    css = client.get("/static/public.css").text
    assert "[data-theme=light]" in css and "Dark only" not in css
    # the CTA button is solid accent, not the old gradient
    assert ".btn-primary,.btn-primary:hover{background:var(--accent)" in css


def test_persian_keyboard_hint_is_client_only(client):
    js = client.get("/static/auth.js").text
    assert "/[\\u0600-\\u06FF]/" in js and "صفحه‌کلید فارسی است. رمز را با صفحه‌کلید انگلیسی بنویسید." in js
    assert "fetch(" not in js and "XMLHttpRequest" not in js and "console." not in js and "sendBeacon" not in js
    # the server never sees or reflects the hint text
    assert "صفحه‌کلید فارسی" not in client.get("/auth").text


def test_reset_stays_admin_only(client):
    page = client.get("/auth").text
    assert "رمزتان را فراموش کردید؟ مدیر سایت می‌تواند آن را بازنشانی کند." in page
    for path in ("/forgot", "/forgot-password", "/reset", "/reset-password", "/auth/reset", "/auth/forgot"):
        assert client.get(path, follow_redirects=False).status_code in (404, 405)
        assert client.post(path, data={}, follow_redirects=False).status_code in (403, 404, 405)


def test_login_flow_used_by_the_android_webview_is_unchanged(client):
    """The app opens /auth in a WebView and follows /auth/continue -> 303 /dashboard with the session cookie."""
    page = client.get("/auth")
    assert page.status_code == 200 and 'action="/auth/continue"' in page.text and 'name="csrf"' in page.text
    assert 'name="username"' in page.text and 'name="password"' in page.text
    assert _signup(client, "droid1").status_code == 303
    _logout(client)
    ok = _continue(client, "droid1", "password123")
    assert ok.status_code == 303 and ok.headers["location"] == "/dashboard" and "session" in ok.headers.get("set-cookie", "")
    assert client.get("/dashboard").status_code == 200
    out = client.post("/logout", data={"csrf": _csrf(client, "/dashboard")}, follow_redirects=False)
    assert out.headers["location"] == "/auth"
    for path in ("/login", "/register"):
        assert client.get(path, follow_redirects=False).headers["location"] == "/auth"
