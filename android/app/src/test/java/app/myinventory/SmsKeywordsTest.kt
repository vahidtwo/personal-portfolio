package app.myinventory

import org.junit.Assert.*
import org.junit.Test

class SmsKeywordsTest {
    private val k = SmsKeywords

    @Test fun normalizeArabicLettersZwnjSpaces() {
        assertEquals("کارت ملی", k.normalize("  كارت\u200C   ملي "))
        assertEquals(k.normalize("خرید‌ها"), k.normalize("خریدها"))
        assertEquals("abc", k.normalize("ABC"))
    }

    @Test fun addRejectsDuplicateEmptyAndSpaced() {
        val l = listOf("برداشت")
        assertTrue(k.add(l, "   ") is SmsKeywords.AddResult.Empty)
        assertTrue(k.add(l, "برداشت") is SmsKeywords.AddResult.Duplicate)
        assertTrue(k.add(l, " برداشت ") is SmsKeywords.AddResult.Duplicate)
        val added = k.add(l, " خرید ") as SmsKeywords.AddResult.Added
        assertEquals(listOf("برداشت", "خرید"), added.list)
        assertTrue(k.add(added.list, "خريد") is SmsKeywords.AddResult.Duplicate)
    }

    @Test fun unlimitedKeywords() {
        var l = listOf("برداشت")
        for (i in 1..30) l = (k.add(l, "کلمه$i") as SmsKeywords.AddResult.Added).list
        assertEquals(31, l.size)
    }

    @Test fun removeLastIsBlocked() {
        assertTrue(k.remove(listOf("برداشت"), "برداشت") is SmsKeywords.RemoveResult.LastOneBlocked)
        val r = k.remove(listOf("برداشت", "خرید"), "برداشت") as SmsKeywords.RemoveResult.Removed
        assertEquals(listOf("خرید"), r.list)
        assertTrue(k.remove(listOf("a", "b"), "c") is SmsKeywords.RemoveResult.NotFound)
    }

    @Test fun matchingNormalizesBothSides() {
        assertTrue(k.matchesAny("خريد از فروشگاه", listOf("خرید")))
        assertTrue(k.matchesAny("برداشت\u200Cاز کارت", listOf("برداشتاز")))
        assertTrue(k.matchesAny("کارت   ملی", listOf("کارت ملی")))
        assertFalse(k.matchesAny("واریز ۱۰۰٬۰۰۰ ریال", listOf("برداشت")))
    }

    @Test fun twoKeywordsGiveOneSpend() {
        val body = "برداشت خرید مبلغ 3,500,000 ریال"
        assertEquals("350000", k.spendAmount(body, listOf("برداشت", "خرید")))
    }

    @Test fun anySenderNoKeywordOrNoAmountIsNothing() {
        assertNull(k.spendAmount("برداشت از حساب شما", listOf("برداشت")))
        assertNull(k.spendAmount("مبلغ 50,000 تومان", listOf("برداشت")))
        assertEquals("50000", k.spendAmount("پرداخت مبلغ ۵۰٬۰۰۰ تومان", listOf("پرداخت")))
    }

    @Test fun noteMasksCardAndDropsBalance() {
        val note = k.cleanNote("برداشت از کارت 6037-9912-3456-7890\nمبلغ 3,500,000 ریال\nمانده 12,345,678 ریال خرید اینترنتی")
        assertFalse(note.contains("6037")); assertFalse(note.contains("7890"))
        assertTrue(note.contains("****"))
        assertTrue(note.contains("3,500,000"))
        assertFalse(note.contains("مانده")); assertFalse(note.contains("12,345,678"))
    }

    @Test fun noteMasksAccountShortCardAndPersianDigits() {
        val n = k.cleanNote("حساب ۰۱۲۳۴۵۶۷۸۹ برداشت ۲۰۰٬۰۰۰ ریال موجودی: ۹٬۹۹۹٬۹۹۹ کارت *1234 کارت 5678")
        assertFalse(n.contains("۰۱۲۳۴۵۶۷۸۹")); assertFalse(n.contains("1234")); assertFalse(n.contains("5678"))
        assertFalse(n.contains("۹٬۹۹۹٬۹۹۹")); assertFalse(n.contains("موجودی"))
        assertTrue(n.contains("۲۰۰٬۰۰۰"))
    }

    @Test fun noteCleanThenCut() {
        val body = "x".repeat(95) + " 1234567890123456"
        val n = k.cleanNote(body)
        assertTrue(n.length <= 100)
        assertFalse(Regex("\\d").containsMatchIn(n))
    }

    @Test fun migration() {
        assertEquals(SmsKeywords.Migration(listOf("برداشت"), true), k.migrate(null, true, ""))
        assertEquals(SmsKeywords.Migration(listOf("برداشت"), true), k.migrate(null, true, "  "))
        assertEquals(SmsKeywords.Migration(listOf("خرید کارت"), false), k.migrate(null, true, " خرید  کارت "))
        assertEquals(SmsKeywords.Migration(listOf("برداشت"), false), k.migrate(null, false, null))
        assertNull(k.migrate("[\"a\"]", true, ""))
        assertEquals(SmsKeywords.Migration(listOf("برداشت"), true), k.migrate("[]", true, ""))
    }

    @Test fun jsonRoundTrip() {
        val l = listOf("برداشت", "خرید \"x\"")
        assertEquals(l, k.fromJson(k.toJson(l)))
        assertEquals(emptyList<String>(), k.fromJson("not json"))
    }
}
