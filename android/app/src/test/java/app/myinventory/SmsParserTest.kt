package app.myinventory

import org.junit.Assert.*
import org.junit.Test

class SmsParserTest {
    private val p = SmsParser

    private val sampleA = "10.8612099.1\n-50,000,000\n08/05_15:38\nمانده: 1,792,003,671"
    private val sampleB = "بانك ملي ايران\nانتقالي:3,620,000-\nحساب:87009\nمانده:18,427,977\n0803-22:34"

    @Test fun sampleAMinusBefore() {
        val r = p.parse(sampleA, "BANK")!!
        assertEquals(-5_000_000L, r.amountToman)
        assertEquals(179_200_367L, r.balanceToman)
        assertEquals(SmsParser.Source.AUTO, r.source)
    }

    @Test fun sampleBMinusAfterArabicLetters() {
        val r = p.parse(sampleB, "BANK")!!
        assertEquals(-362_000L, r.amountToman)
        assertEquals(1_842_797L, r.balanceToman)
        assertEquals(SmsParser.Source.AUTO, r.source)
    }

    @Test fun samplesOnOneLineWithSlashes() {
        assertEquals(-5_000_000L, p.parse("10.8612099.1 / -50,000,000 / 08/05_15:38 / مانده: 1,792,003,671", "")!!.amountToman)
        assertEquals(-362_000L, p.parse("بانك ملي ايران / انتقالي:3,620,000- / حساب:87009 / مانده:18,427,977 / 0803-22:34", "")!!.amountToman)
    }

    @Test fun normalizeLettersDigitsSeparators() {
        assertEquals("بانک ملی ایران", p.normalize("بانك ملي ايران"))
        assertEquals("1234567", p.normalize("۱٬۲۳۴٬۵۶۷"))
        assertEquals("1234567", p.normalize("١,٢٣٤,٥٦٧"))
        assertEquals("-50", p.normalize("\u221250"))
        assertEquals("a, b", p.normalize("a, b"))
    }

    @Test fun persianDigitsAndMinusVariants() {
        assertEquals(-5_000_000L, p.parse("برداشت\n-۵۰٬۰۰۰٬۰۰۰\nمانده: ۱۰۰", "")!!.amountToman)
        assertEquals(-5_000_000L, p.parse("برداشت\n٥٠,٠٠٠,٠٠٠-\nمانده: ١٠٠", "")!!.amountToman)
        assertEquals(-5_000_000L, p.parse("\u221250,000,000", "")!!.amountToman)
        assertEquals(-5_000_000L, p.parse("\u200F-50,000,000\u200F", "")!!.amountToman)
    }

    @Test fun balanceIsNeverTheAmount() {
        assertNull(p.parse("حساب 12345\nمانده: -1,000,000", ""))
        assertNull(p.parse("مانده:1,000,000-", ""))
        assertEquals(-100L, p.parse("-1,000\nمانده:-2,000", "")!!.amountToman)
        assertEquals(-100L, p.parse("-1,000\nموجودی: 2,000-", "")!!.amountToman)
    }

    @Test fun datesTimesAndAccountsAreNotAmounts() {
        assertTrue(p.minusCandidates("0803-22:34\n1405-08-05\n10.8612099.1\n08/05_15:38").isEmpty())
        assertEquals(listOf(10_000L), p.minusCandidates("1405-08-05 -10,000"))
    }

    @Test fun depositsAndUnsignedAreIgnored() {
        assertNull(p.parse("واریز:3,620,000+\nمانده:18,427,977", ""))
        assertNull(p.parse("واریز 3,620,000\nمانده:18,427,977", ""))
        assertNull(p.parse("خرید 3,620,000 ریال", ""))
        assertNull(p.parse("", ""))
    }

    @Test fun severalCandidatesAreNotConfident() {
        assertNull(p.autoDetect("-1,000\n-2,000"))
        assertNull(p.parse("-1,000\n2,000-", "BANK"))
    }

    @Test fun tooSmallForATomanIsIgnored() {
        assertNull(p.parse("-9", ""))
        assertEquals(-1L, p.parse("-19", "")!!.amountToman)
    }

    private fun template(sample: String, amount: String, sender: String = "BANK", out: Boolean? = null) =
        SmsParser.Template(sender, sample, sample.indexOf(amount), sample.indexOf(amount) + amount.length, out)

    private val tSample = "بانك تست\nبرداشت مبلغ 1,250,000 ريال\nحساب 1111\n1405/08/05 10:00\nمانده 9,999,999"

    @Test fun templateFallbackWhenNoSign() {
        val t = template(tSample, "1,250,000")
        val sms = "بانک تست\nبرداشت مبلغ ۳۰۰٬۰۰۰ ریال\nحساب 1111\n1405/08/06 21:15\nمانده 8,000,000"
        assertNull(p.autoDetect(sms))
        assertNull(p.parse(sms, "bank", listOf(t)))  // no minus sign: never a spend, even with «برداشت»
    }

    @Test fun templateNeedsSameSenderAndShape() {
        val t = template(tSample, "1,250,000")
        val sms = "بانک تست\nبرداشت مبلغ 300,000 ریال\nحساب 1111\n1405/08/06 21:15\nمانده 8,000,000"
        assertNull(p.parse(sms, "OTHER", listOf(t)))
        assertNull(p.parse("پیام دیگر 300,000", "BANK", listOf(t)))
    }

    @Test fun templateDirectionFromUserWhenNoKeyword() {
        val sample = "بانک\nمبلغ 1,000,000\nمانده 5"
        val sms = "بانک\nمبلغ 2,000,000\nمانده 5"
        assertNull(p.parse(sms, "BANK", listOf(template(sample, "1,000,000"))))
        assertNull(p.parse(sms, "BANK", listOf(template(sample, "1,000,000", out = false))))
        assertNull(p.parse(sms, "BANK", listOf(template(sample, "1,000,000", out = true))))  // saved answer no longer counts
    }

    @Test fun templateDepositIsIgnored() {
        val sample = "بانک\nواریز 1,000,000\nمانده 5"
        assertNull(p.parse("بانک\nواریز 2,000,000\nمانده 5", "BANK", listOf(template(sample, "1,000,000", out = true))))
    }

    @Test fun templateNotUsedWhenAutoIsConfident() {
        val t = template(tSample, "1,250,000")
        assertEquals(SmsParser.Source.AUTO, p.parse(sampleA, "BANK", listOf(t))!!.source)
    }

    @Test fun templateUsedWhenAutoHasSeveral() {
        val sample = "بانک\nخرید 1,000,000-\nکارمزد 5,000-\nمانده 5"
        val t = template(sample, "1,000,000")
        val r = p.parse("بانک\nخرید 2,000,000-\nکارمزد 7,000-\nمانده 5", "BANK", listOf(t))!!
        assertEquals(-200_000L, r.amountToman)
        assertEquals(SmsParser.Source.TEMPLATE, r.source)
    }

    @Test fun badTemplateRangesAreSkipped() {
        assertNull(p.templateRegex(SmsParser.Template("B", "abc", 2, 1)))
        assertNull(p.templateRegex(SmsParser.Template("B", "abc", 0, 99)))
        assertNull(p.templateRegex(SmsParser.Template("B", "abc", 0, 2)))
        assertNull(p.parse("abc", "B", listOf(SmsParser.Template("B", "abc", 0, 2, true))))
    }

    @Test fun templateLiteralTextIsEscaped() {
        val sample = "(x) [1,000] *"
        val t = template(sample, "1,000", out = true)
        assertEquals(-200L, p.parse("(x) [2,000-] *", "BANK", listOf(t))!!.amountToman)
        assertNull(p.matchTemplate("(x) {2,000-} *", "BANK", listOf(t)))
    }

    @Test fun plusAndMoneyInWordsAreMoneyIn() {
        assertTrue(p.isMoneyIn("+1,000"))
        assertTrue(p.isMoneyIn("1,000+"))
        assertTrue(p.isMoneyIn("1,000 +"))
        assertTrue(p.isMoneyIn("واريز 1,000"))  // Arabic yeh
        assertTrue(p.isMoneyIn("افزایش 1,000"))
        assertFalse(p.isMoneyIn("-1,000\nمانده 5"))
        assertNull(p.autoDetect("+50,000\n-1,000\nمانده 5"))
    }
}
