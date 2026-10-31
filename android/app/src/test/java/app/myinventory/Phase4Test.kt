package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class Phase4Test {
    @Test fun persianDigits() = assertEquals("۱۲٬۳", Fa.digits("12٬3"))

    @Test fun lockedMinutesRoundUp() {
        assertEquals(1, Fa.minutes(1))
        assertEquals(15, Fa.minutes(900))
        assertEquals(16, Fa.minutes(901))
        assertEquals("دوباره امتحان کنید، ۱۵ دقیقهٔ دیگر", Fa.lockedButton(900))
    }

    @Test fun persianKeyboardHint() {
        assertTrue(Fa.hasPersianLetter("abcش"))
        assertFalse(Fa.hasPersianLetter("abc123"))
        assertFalse(Fa.hasPersianLetter("۱۲۳"))
    }

    @Test fun cookieValues() {
        val h = "inventory_session=abc.def; inventory_signed_in=1; inventory_page_key=uXYZ"
        assertEquals("1", CookieJar.value(h, "inventory_signed_in"))
        assertEquals("uXYZ", CookieJar.value(h, "inventory_page_key"))
        assertNull(CookieJar.value(h, "other"))
        assertNull(CookieJar.value(null, "inventory_signed_in"))
    }

    @Test fun cacheKeyIsVersionAndUser() {
        assertEquals("v13:uA", HomeCache.key(13, "uA"))
        assertNull(HomeCache.key(13, null))
        assertNull(HomeCache.key(13, ""))
        assertFalse(HomeCache.key(13, "uA") == HomeCache.key(14, "uA"))
        assertFalse(HomeCache.key(13, "uA") == HomeCache.key(13, "uB"))
    }

    @Test fun biometricOffByDefault() = assertFalse(BuildConfig.BIOMETRIC_UNLOCK)

    @Test fun hideAmountsDefaultsToHidden() {
        assertTrue(HomeActivity.MASK_DEFAULT)
    }

    @Test fun retryReloadsFailedUrlOnlyOnAppOrigin() {
        val base = "https://daraiito.ir"
        assertEquals("https://daraiito.ir/stocks?x=1", MainActivity.retryTarget("https://daraiito.ir/stocks?x=1", base))
        assertEquals("https://daraiito.ir/dashboard", MainActivity.retryTarget(null, base))
        assertEquals("https://daraiito.ir/dashboard", MainActivity.retryTarget("https://evil.example/x", base))
        assertEquals("https://daraiito.ir/dashboard", MainActivity.retryTarget("file:///android_asset/www/error.html", base))
    }

    @Test fun maskedNetUnitHidesMagnitude() {
        assertEquals("تومان", MaskRules.netUnit(true, "میلیون تومان"))
        assertEquals("میلیون تومان", MaskRules.netUnit(false, "میلیون تومان"))
    }

    @Test fun maskedTodayLineHidesAmount() {
        assertEquals("امروز: ••••••", MaskRules.todayLine(true, "۰"))
        assertEquals("امروز: ۱۲ تومان", MaskRules.todayLine(false, "۱۲"))
    }

    @Test fun sparklineColoursFollowTrend() {
        assertEquals(0xFF08735A.toInt(), MaskRules.trendColor("up", false))
        assertEquals(0xFFB42318.toInt(), MaskRules.trendColor("down", false))
        assertEquals(0xFF5B6475.toInt(), MaskRules.trendColor("flat", false))
        assertEquals(0xFF3EE0B8.toInt(), MaskRules.trendColor("up", true))
        assertEquals(0xFFFF8A7A.toInt(), MaskRules.trendColor("down", true))
        assertEquals(0xFF9AA3B2.toInt(), MaskRules.trendColor("flat", true))
    }

    @Test fun keyboardScrollShowsSubmitPlusMargin() {
        assertEquals(116, KeyboardScroll.target(1000, 16, 1200, 300))
        assertEquals(0, KeyboardScroll.target(400, 16, 1200, 300))
    }
}
