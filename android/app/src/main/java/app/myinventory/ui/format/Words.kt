package app.myinventory.ui.format

private val ONES = listOf("", "یک", "دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه")
private val TEENS = listOf("ده", "یازده", "دوازده", "سیزده", "چهارده", "پانزده", "شانزده", "هفده", "هجده", "نوزده")
private val TENS = listOf("", "", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود")
private val HUNDREDS = listOf("", "صد", "دویست", "سیصد", "چهارصد", "پانصد", "ششصد", "هفتصد", "هشتصد", "نهصد")
private val SCALES = listOf("", "هزار", "میلیون", "میلیارد", "تریلیون", "کوادریلیون")

private fun under1000(n: Int): String {
    val parts = mutableListOf<String>()
    if (n >= 100) parts += HUNDREDS[n / 100]
    val r = n % 100
    when {
        r >= 20 -> { parts += TENS[r / 10]; if (r % 10 > 0) parts += ONES[r % 10] }
        r >= 10 -> parts += TEENS[r - 10]
        r > 0 -> parts += ONES[r]
    }
    return parts.joinToString(" و ")
}

/** 48000000 → «چهل و هشت میلیون». The typo guard under an amount field. */
fun faWords(value: Long): String {
    if (value == 0L) return "صفر"
    var n = kotlin.math.abs(value)
    val groups = mutableListOf<String>()
    var scale = 0
    while (n > 0) {
        val g = (n % 1000).toInt()
        if (g > 0) {
            val words = if (g == 1 && scale == 1) "" else under1000(g)
            groups += listOf(words, SCALES[scale]).filter { it.isNotEmpty() }.joinToString(" ")
        }
        n /= 1000
        scale++
    }
    return (if (value < 0) "منفی " else "") + groups.reversed().joinToString(" و ")
}

/** «چهل و هشت میلیون تومان» for the typed digits, or null when there is nothing to read. */
fun amountWordsLine(digits: String): String? = digits.toLongOrNull()?.let { "${faWords(it)} تومان" }
