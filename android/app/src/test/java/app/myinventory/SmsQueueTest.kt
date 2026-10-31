package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Test

class SmsQueueTest {
    private fun e(k: String, t: Long = 1L, u: String = "alice") = SmsQueue.Entry("120000", "خرید ****1234", k, t, u)
    private val day = 24L * 60 * 60 * 1000
    private val now = 1_800_000_000_000L

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

    @Test fun matchingUserIsSent() {
        val (send, keep) = SmsQueue.split(listOf(e("a", now - day, "Alice")), "alice", now)
        assertEquals(listOf("a"), send.map { it.idem }); assertEquals(0, keep.size)
    }

    @Test fun differentUserSendsNothingAndKeeps() {
        val q = listOf(e("a", now - day, "alice"))
        val (send, keep) = SmsQueue.split(q, "bob", now)
        assertEquals(0, send.size); assertEquals(q, keep)
    }

    @Test fun unknownUserSendsNothing() = assertEquals(0, SmsQueue.split(listOf(e("a", now, "alice")), "", now).first.size)

    @Test fun olderThanSevenDaysDropped() {
        val q = listOf(e("old", now - 7 * day - 1, "alice"), e("edge", now - 7 * day, "alice"), e("bob-old", now - 8 * day, "bob"))
        val (send, keep) = SmsQueue.split(q, "alice", now)
        assertEquals(listOf("edge"), send.map { it.idem }); assertEquals(0, keep.size)
    }

    @Test fun userSurvivesRoundTrip() = assertEquals("alice", SmsQueue.decode(SmsQueue.encode(listOf(e("a")))).single().user)
}
