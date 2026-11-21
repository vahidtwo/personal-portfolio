package app.myinventory

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PriceRefreshTest {
    @Test fun okReloadsHomeWithServerMessage() {
        val o = PriceRefresh.outcome(200, JSONObject().put("result", "ok").put("message", "قیمت بازار و پرتفوی به‌روز شد"))
        assertEquals(PriceRefresh.Next.RELOAD_HOME, o.next)
        assertEquals("قیمت بازار و پرتفوی به‌روز شد", o.message)
    }

    @Test fun cooldownAndErrorStillReloadHome() {
        val wait = PriceRefresh.outcome(429, JSONObject().put("result", "wait").put("message", "حدود ۴ دقیقه دیگر"))
        assertEquals(PriceRefresh.Next.RELOAD_HOME, wait.next)
        assertEquals("حدود ۴ دقیقه دیگر", wait.message)
        assertEquals(PriceRefresh.FAILED_MESSAGE, PriceRefresh.outcome(500, JSONObject()).message)
    }

    @Test fun offlineAndSignedOut() {
        assertEquals(PriceRefresh.OFFLINE_MESSAGE, PriceRefresh.outcome(null, null).message)
        assertEquals(PriceRefresh.Next.SIGN_OUT, PriceRefresh.outcome(401, JSONObject()).next)
    }

    @Test fun waitLabelOnlyDuringCooldown() {
        assertNull(PriceRefresh.waitLabel(null))
        assertNull(PriceRefresh.waitLabel(JSONObject().put("state", "stale")))
        assertNull(PriceRefresh.waitLabel(JSONObject().put("wait_sec", 0).put("wait_label", "")))
        assertEquals("دوباره تا ۳ دقیقه", PriceRefresh.waitLabel(JSONObject().put("wait_sec", 170).put("wait_label", "دوباره تا ۳ دقیقه")))
    }

    @Test fun callWaitsLongerThanTheServerFetch() {
        assertEquals("/api/home/refresh-prices", PriceRefresh.PATH)
        assertTrue(PriceRefresh.TIMEOUT_MS >= 60_000)
    }
}
