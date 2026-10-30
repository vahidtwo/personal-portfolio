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
}
