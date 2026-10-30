package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Test

class SmsQueueTest {
    private fun e(k: String, t: Long = 1L) = SmsQueue.Entry("120000", "خرید ****1234", k, t)

    @Test fun roundTrip() {
        val list = listOf(e("a", 10), e("b", 20))
        assertEquals(list, SmsQueue.decode(SmsQueue.encode(list)))
    }

    @Test fun badDataDecodesEmpty() = assertEquals(emptyList<SmsQueue.Entry>(), SmsQueue.decode("nope"))

    @Test fun sameKeyQueuedOnce() {
        val q = SmsQueue.added(SmsQueue.added(emptyList(), e("a")), e("a"))
        assertEquals(1, q.size)
    }

    @Test fun capDropsOldest() {
        var q = emptyList<SmsQueue.Entry>()
        repeat(SmsQueue.MAX_ENTRIES + 3) { q = SmsQueue.added(q, e("k$it")) }
        assertEquals(SmsQueue.MAX_ENTRIES, q.size)
        assertEquals("k3", q.first().idem)
    }

    @Test fun classify() {
        assertEquals(SmsQueue.Result.DONE, SmsQueue.classify(200))
        assertEquals(SmsQueue.Result.KEEP_AND_STOP, SmsQueue.classify(401))
        assertEquals(SmsQueue.Result.KEEP_AND_STOP, SmsQueue.classify(302))
        assertEquals(SmsQueue.Result.DROP, SmsQueue.classify(400))
        assertEquals(SmsQueue.Result.KEEP, SmsQueue.classify(503))
        assertEquals(SmsQueue.Result.KEEP, SmsQueue.classify(null))
    }

    @Test fun payloadReusesKeyAndTime() {
        val p = SmsQueue.payload(e("idem-1", 1700000000000))
        assertEquals("idem-1", p.getString("idempotency_key"))
        assertEquals(1700000000000, p.getLong("sms_at"))
        assertEquals("120000", p.getString("amount_toman"))
    }
}
