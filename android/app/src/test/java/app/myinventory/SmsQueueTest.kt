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

    // 12.1.2: failed live sends (network / 5xx) go to the same queue and are retried.
    @Test fun networkErrorAnd5xxAreQueuedForRetry() {
        for (c in listOf(null, 500, 502, 503, 504)) {
            org.junit.Assert.assertTrue("$c", ServerAddress.retryLater(c))
            assertEquals(ServerAddress.SmsOutcome.FAILED, ServerAddress.smsOutcome(c))
            assertEquals(SmsQueue.Result.KEEP, SmsQueue.classify(c))
        }
    }

    @Test fun badRequestsAndSuccessAreNotRetried() {
        for (c in listOf(200, 201, 301, 400, 401, 403, 404, 422)) org.junit.Assert.assertFalse("$c", ServerAddress.retryLater(c))
    }

    @Test fun failedSendQueuedTwiceIsOneEntryAndFlushesOnceForItsUser() {
        var q = SmsQueue.added(emptyList(), e("fail", now - day, "alice"))
        q = SmsQueue.added(q, e("fail", now, "alice"))   // the same SMS failing again
        q = SmsQueue.added(q, e("bob1", now, "bob"))
        assertEquals(2, q.size)
        val (send, keep) = SmsQueue.split(q, "Alice", now)
        assertEquals(listOf("fail"), send.map { it.idem }); assertEquals(listOf("bob1"), keep.map { it.idem })
        assertEquals("fail", SmsQueue.payload(send.single()).getString("idempotency_key"))
    }

    @Test fun failedSendExpiresAfterSevenDays() {
        val q = listOf(e("old", now - 8 * day), e("new", now - 6 * day))
        assertEquals(listOf("new"), SmsQueue.split(q, "alice", now).first.map { it.idem })
    }
}
