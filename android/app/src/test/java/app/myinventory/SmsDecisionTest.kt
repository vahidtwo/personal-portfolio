package app.myinventory

import org.junit.Assert.*
import org.junit.Test

class SmsDecisionTest {
    private val d = SmsDecision
    private val kw = listOf(SmsKeywords.DEFAULT)

    private val sampleA = "10.8612099.1\n-50,000,000\n08/05_15:38\nمانده: 1,792,003,671"
    private val sampleB = "بانك ملي ايران\nانتقالي:3,620,000-\nحساب:87009\nمانده:18,427,977\n0803-22:34"

    @Test fun sampleAEndToEnd() {
        val s = d.decide(sampleA, "+980000000", kw)!!
        assertEquals("5000000", s.amountToman)
        assertEquals(SmsDecision.Path.AUTO, s.path)
        assertFalse(s.note.contains("1792003671") || s.note.contains("1,792,003,671"))
        assertFalse(s.note.contains("8612099"))
    }

    @Test fun sampleBEndToEnd() {
        val s = d.decide(sampleB, "BANK", kw)!!
        assertEquals("362000", s.amountToman)
        assertEquals(SmsDecision.Path.AUTO, s.path)
        assertFalse(s.note.contains("18,427,977"))
        assertFalse(s.note.contains("87009"))
    }

    @Test fun autoNeedsABalanceLine() {
        assertNull(d.decide("سلام -50,000 ممنون", "+980000001", kw))
    }

    @Test fun otpIsSkipped() {
        assertNull(d.decide("رمز پویا: 123456\n-50,000\nمانده: 1,000", "BANK", kw))
        assertNull(d.decide("OTP 123456 -50,000 مانده 1,000", "BANK", kw))
        assertNull(d.decide("کد تایید 1234\nبرداشت 50,000 ریال", "BANK", kw))
    }

    @Test fun keywordGateStillWorksWithRialRule() {
        val s = d.decide("برداشت 120,000\nحساب ****", "BANK", kw)!!
        assertEquals("12000", s.amountToman)
        assertEquals(SmsDecision.Path.KEYWORD, s.path)
        assertEquals("120000", d.decide("برداشت 120,000 تومان", "BANK", kw)!!.amountToman)
        assertEquals("12000", d.decide("برداشت 120,000 ریال", "BANK", kw)!!.amountToman)
    }

    @Test fun tomanLabelKeepsAutoAmount() {
        assertEquals("50000", d.decide("-50,000 تومان\nمانده: 1,000", "BANK", kw)!!.amountToman)
    }

    @Test fun noGateNoSpend() {
        assertNull(d.decide("خرید 50,000 ریال", "BANK", kw))
        assertNull(d.decide("واریز 50,000\nمانده: 1,000", "BANK", kw))
        assertNull(d.decide("", "BANK", kw))
    }

    @Test fun templateSenderPath() {
        val sample = "بانک تست\nمبلغ 1,000,000\nتاریخ 1405/08/05-10:00\nمانده 5"
        val start = sample.indexOf("1,000,000")
        val t = SmsParser.Template("TESTBANK", sample, start, start + 9, true)
        val sms = "بانک تست\nمبلغ 2,000,000\nتاریخ 1405/08/06-21:15\nمانده 7"
        val s = d.decide(sms, "TESTBANK", emptyList(), listOf(t))!!
        assertEquals("200000", s.amountToman)
        assertEquals(SmsDecision.Path.TEMPLATE, s.path)
        assertNull(d.decide(sms, "OTHER", emptyList(), listOf(t)))
    }

    @Test fun templateJsonRoundTripAndBadInput() {
        val t = SmsParser.Template("S", "x 1 y", 2, 3, null)
        val u = SmsParser.Template("S2", "x 1 y", 2, 3, true)
        assertEquals(listOf(t, u), d.templatesFromJson(d.templatesToJson(listOf(t, u))))
        assertEquals(emptyList<SmsParser.Template>(), d.templatesFromJson(null))
        assertEquals(emptyList<SmsParser.Template>(), d.templatesFromJson("not json"))
        assertEquals(listOf(t), d.templatesFromJson("[{\"bad\":1}," + d.templatesToJson(listOf(t)).drop(1)))
    }

    @Test fun smsLogPruneAndJson() {
        val now = 1_000_000_000_000L
        val day = 24L * 60 * 60 * 1000
        val old = SmsLog.Entry(now - 91 * day, "S", "old")
        val future = SmsLog.Entry(now + day, "S", "future")
        val many = (1..250).map { SmsLog.Entry(now - it * 1000L, "S", "b$it") }
        val kept = SmsLog.prune(many + old + future, now)
        assertEquals(SmsLog.MAX_ENTRIES, kept.size)
        assertEquals("b1", kept.last().body)
        assertFalse(kept.any { it.body == "old" || it.body == "future" })
        assertEquals(kept, SmsLog.fromJson(SmsLog.toJson(kept)))
        assertEquals(emptyList<SmsLog.Entry>(), SmsLog.fromJson("{"))
    }

    @Test
    fun purchaseWithTrackingCodeIsSaved() {
        val body = "خرید\n-1,250,000\nکد پیگیری 778812\nمانده 9,000,000"
        val s = d.decide(body, "BANK", kw)!!
        assertEquals("125000", s.amountToman)
        assertEquals(SmsDecision.Path.AUTO, s.path)
    }

    @Test
    fun eachSkipPhraseIsSkipped() {
        val phrases = listOf(
            "رمز", "رمز پویا", "OTP", "otp", "کد تایید", "کد تأیید", "کد تائید", "كد تاييد", "کدتایید",
            "کد فعالسازی", "کد فعال‌سازی", "کد فعال سازی", "کد‌فعالسازی", "Verification", "VERIFICATION code",
        )
        for (p in phrases) {
            val body = "$p 4821\n-1,250,000\nمانده 9,000,000"
            assertTrue(p, SmsParser.isOtp(body))
            assertNull(p, d.decide(body, "BANK", kw))
        }
    }

    @Test
    fun bareCodeDoesNotSkip() {
        assertFalse(SmsParser.isOtp("کد پیگیری 778812"))
        assertFalse(SmsParser.isOtp("کد شعبه 12"))
    }
}
