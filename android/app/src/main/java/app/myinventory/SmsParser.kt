package app.myinventory

/**
 * Pure bank-SMS parsing (no Android APIs, unit-tested on the JVM).
 *
 * Auto-detect first: after normalizing, the withdrawal is the one number with a minus sign directly
 * before or after it. The number after «مانده»/«موجودی» is the balance, never the amount. A user template
 * is used only when auto-detect finds no candidate or more than one. SMS amounts are in rial; results
 * are in toman (rial / 10, rounded down).
 * Only a number with a minus sign is a spend, on every path. Money in (a plus sign next to a number, or
 * «واریز», «افزایش», «بستانکار», «انتقال به حساب شما») is never a spend: see [isMoneyIn].
 */
object SmsParser {
    enum class Source { AUTO, TEMPLATE }

    /** [amountToman] is negative (money out). [balanceToman] is null when the SMS has none. */
    data class Result(val amountToman: Long, val balanceToman: Long?, val source: Source)

    /**
     * A user template: one sample SMS (as received) with the amount marked by its character range
     * [amountStart, amountEnd) in the sample. [out] is the user's answer for SMS with no sign or keyword.
     */
    data class Template(
        val sender: String,
        val sample: String,
        val amountStart: Int,
        val amountEnd: Int,
        val out: Boolean? = null,
    )

    private const val BALANCE_WORDS = "مانده|موجودی"
    private val SPACES = Regex("[ \\t\\u00A0\\u2000-\\u200B\\u202F\\u205F\\u3000]+")
    private val GROUPED = Regex("""(?<=\d)[,٬](?=\d)""")
    private val BALANCE = Regex("""(?:$BALANCE_WORDS)\s*[:：]?\s*-?\s*(\d+)-?""")
    private val MINUS_BEFORE = Regex("""(?<![\d.\-])-\s?(\d+)(?![\d.])""")
    private val MINUS_AFTER = Regex("""(?<![\d.])(\d+)\s?-(?![\d\-])""")
    private val IN_WORDS = listOf("واریز", "افزایش", "بستانکار", "انتقال به حساب شما", "دریافتی")
    private val PLUS_NUMBER = Regex("""\+\s?\d|\d\s?\+""")

    /** True for any money-in SMS: a plus-signed number or a money-in word. Such an SMS is never a spend. */
    fun isMoneyIn(body: String): Boolean {
        val t = normalize(body)
        return PLUS_NUMBER.containsMatchIn(t) || IN_WORDS.any { t.contains(it) }
    }

    /** ي/ى→ی, ك→ک, Persian/Arabic digits→ASCII, other minus signs→'-', thousands separators removed. */
    fun normalize(text: String): String {
        val sb = StringBuilder(text.length)
        for (ch in text) {
            when (ch) {
                'ي', 'ى' -> sb.append('ی')
                'ك' -> sb.append('ک')
                in '۰'..'۹' -> sb.append('0' + (ch - '۰'))
                in '٠'..'٩' -> sb.append('0' + (ch - '٠'))
                '\u2212', '\u2012', '\u2013', '\u2014', '\uFE63', '\uFF0D' -> sb.append('-')
                '\u200C', '\u200D', '\u200E', '\u200F', '\u202A', '\u202B', '\u202C', '\u202D', '\u202E',
                '\u2066', '\u2067', '\u2068', '\u2069', '\uFEFF' -> {}
                else -> sb.append(ch)
            }
        }
        return SPACES.replace(GROUPED.replace(sb.toString(), ""), " ")
    }

    fun toToman(rial: Long): Long = rial / 10

    /** True when the SMS labels its amounts «تومان» (or "toman"); every other SMS amount is rial. */
    fun labeledToman(body: String): Boolean {
        val t = normalize(body).lowercase()
        return t.contains("تومان") || t.contains("toman")
    }

    /** SMS number to toman: as is when labeled «تومان», otherwise rial / 10. */
    fun amountToman(body: String, value: Long): Long = if (labeledToman(body)) value else toToman(value)

    private val OTP = Regex(
        """رمز|otp|verification|کد[\s\u200c]*ت(?:أی|اٴی|ائ|ای)ید|کد[\s\u200c]*فعال[\s\u200c]*سازی""",
        RegexOption.IGNORE_CASE,
    )

    /** Password, OTP, confirmation and activation messages are never spends; a bare «کد» is not enough. */
    fun isOtp(body: String): Boolean = OTP.containsMatchIn(normalize(body))

    fun hasBalanceLine(body: String): Boolean = normalize(body).contains("مانده")

    /** Balance in toman from the number after «مانده»/«موجودی», or null. */
    fun balanceToman(body: String): Long? =
        BALANCE.find(normalize(body))?.groupValues?.get(1)?.toLongOrNull()?.let { toToman(it) }

    /** Rial values of every signed number outside the balance segment. */
    fun minusCandidates(body: String): List<Long> {
        val text = BALANCE.replace(normalize(body)) { " ".repeat(it.value.length) }
        val found = sortedMapOf<Int, Long>()
        for (re in listOf(MINUS_BEFORE, MINUS_AFTER)) {
            re.findAll(text).forEach { m ->
                val g = m.groups[1]!!
                g.value.toLongOrNull()?.let { found[g.range.first] = it }
            }
        }
        return found.values.toList()
    }

    /** The withdrawal when exactly one signed number is found; null for none or several. */
    fun autoDetect(body: String): Result? {
        if (isMoneyIn(body)) return null
        val c = minusCandidates(body)
        if (c.size != 1) return null
        val toman = amountToman(body, c[0])
        if (toman <= 0) return null
        return Result(-toman, balanceToman(body), Source.AUTO)
    }

    /** Regex for a template: unmarked numbers match `[\d,/.:_-]+`, the marked amount is a group, other text is literal. */
    fun templateRegex(t: Template): Regex? {
        if (t.amountStart < 0 || t.amountEnd > t.sample.length || t.amountStart >= t.amountEnd) return null
        val before = normalize(t.sample.substring(0, t.amountStart))
        val amount = normalize(t.sample.substring(t.amountStart, t.amountEnd))
        val after = normalize(t.sample.substring(t.amountEnd))
        if (!amount.contains(Regex("""\d"""))) return null
        return Regex("^\\s*" + literal(before) + "-?\\s?(\\d+)\\s?-?" + literal(after) + "\\s*$")
    }

    private fun literal(s: String): String {
        val out = StringBuilder()
        val parts = Regex("""\d[\d,/.:_-]*|\s+""")
        var last = 0
        for (m in parts.findAll(s)) {
            if (m.range.first > last) out.append(Regex.escape(s.substring(last, m.range.first)))
            out.append(if (m.value[0].isDigit()) "[\\d,/.:_-]+" else "\\s+")
            last = m.range.last + 1
        }
        if (last < s.length) out.append(Regex.escape(s.substring(last)))
        return out.toString()
    }

    private fun sameSender(a: String, b: String): Boolean =
        normalize(a).trim().lowercase() == normalize(b).trim().lowercase()

    /** Template match for this sender, or null (no match, a deposit, or the direction is unknown). */
    fun matchTemplate(body: String, sender: String, templates: List<Template>): Result? {
        val text = normalize(body)
        for (t in templates) {
            if (!sameSender(t.sender, sender)) continue
            val m = templateRegex(t)?.find(text) ?: continue
            val g = m.groups[1] ?: continue
            val rial = g.value.toLongOrNull() ?: continue
            val signed = text.substring(0, g.range.first).trimEnd().endsWith("-") ||
                text.substring(g.range.last + 1).trimStart().startsWith("-")
            // Minus sign only: the template's saved in/out answer and out-words no longer make a spend.
            if (!signed || isMoneyIn(body)) return null
            val toman = amountToman(body, rial)
            if (toman <= 0) return null
            return Result(-toman, balanceToman(body), Source.TEMPLATE)
        }
        return null
    }

    /** One decision per SMS: auto-detect first, the user's templates only when that is not confident. */
    fun parse(body: String, sender: String, templates: List<Template> = emptyList()): Result? =
        if (isMoneyIn(body)) null else autoDetect(body) ?: matchTemplate(body, sender, templates)
}
