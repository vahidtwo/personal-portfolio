package app.myinventory

import org.json.JSONArray

/**
 * Pure SMS keyword logic (no Android APIs, unit-tested on the JVM).
 * Keywords live on the phone only; nothing here talks to the network.
 */
object SmsKeywords {
    const val DEFAULT = "برداشت"

    sealed class AddResult {
        data class Added(val list: List<String>) : AddResult()
        object Empty : AddResult()
        object Duplicate : AddResult()
    }

    sealed class RemoveResult {
        data class Removed(val list: List<String>) : RemoveResult()
        object LastOneBlocked : RemoveResult()
        object NotFound : RemoveResult()
    }

    data class Migration(val keywords: List<String>, val showUpgradeNote: Boolean)

    private val SPACES = Regex("[\\s\\u00A0\\u2000-\\u200B\\u202F\\u205F\\u3000]+")

    /** Comparison form: ي→ی, ك→ک, no ZWNJ/ZWJ, one space between words, trimmed, Latin lowercase. */
    fun normalize(text: String): String {
        val sb = StringBuilder(text.length)
        for (ch in text) {
            when (ch) {
                'ي', 'ى' -> sb.append('ی')
                'ك' -> sb.append('ک')
                '\u200C', '\u200D', '\u200E', '\u200F', '\uFEFF' -> {}
                else -> sb.append(ch)
            }
        }
        return SPACES.replace(sb.toString(), " ").trim().lowercase()
    }

    /** Display form: the user's spelling, trimmed and with single spaces. */
    fun clean(text: String): String = SPACES.replace(text, " ").trim()

    fun add(list: List<String>, raw: String): AddResult {
        val word = clean(raw)
        if (normalize(word).isEmpty()) return AddResult.Empty
        val key = normalize(word)
        if (list.any { normalize(it) == key }) return AddResult.Duplicate
        return AddResult.Added(list + word)
    }

    fun remove(list: List<String>, word: String): RemoveResult {
        val i = list.indexOf(word).takeIf { it >= 0 }
            ?: list.indexOfFirst { normalize(it) == normalize(word) }.takeIf { it >= 0 }
            ?: return RemoveResult.NotFound
        if (list.size <= 1) return RemoveResult.LastOneBlocked
        return RemoveResult.Removed(list.toMutableList().also { it.removeAt(i) })
    }

    /** True when the body contains at least one keyword (once, however many match). */
    fun matchesAny(body: String, keywords: List<String>): Boolean {
        val b = normalize(body)
        return keywords.map { normalize(it) }.filter { it.isNotEmpty() }.any { b.contains(it) }
    }

    /** One decision per SMS: the amount in tomans to record, or null. */
    fun spendAmount(body: String, keywords: List<String>): String? =
        if (matchesAny(body, keywords)) parseAmount(body) else null

    private val AMOUNT_PATTERNS = listOf(
        Regex("""(?:مبلغ|برداشت|withdraw)[^\d]{0,20}(\d[\d,٬]*)""", RegexOption.IGNORE_CASE),
        Regex("""(\d[\d,٬]{3,})\s*(?:ریال|تومان|Rial|Toman)""", RegexOption.IGNORE_CASE),
    )

    /** The amount number as written in the SMS (no unit applied), or null. */
    fun rawAmount(body: String): Long? {
        val normalized = toLatinDigits(body)
        val raw = AMOUNT_PATTERNS.firstNotNullOfOrNull { it.find(normalized)?.groupValues?.get(1) } ?: return null
        val value = raw.replace(",", "").replace("٬", "").toLongOrNull() ?: return null
        return if (value > 0) value else null
    }

    fun parseAmount(body: String): String? {
        val value = rawAmount(body) ?: return null
        val lower = body.lowercase()
        val rial = (lower.contains("ریال") || lower.contains("rial")) && !lower.contains("تومان") && !lower.contains("toman")
        val toman = if (rial) value / 10 else value
        return if (toman > 0) toman.toString() else null
    }

    private fun toLatinDigits(s: String): String = s.map { ch ->
        when (ch) {
            in '۰'..'۹' -> '0' + (ch - '۰')
            in '٠'..'٩' -> '0' + (ch - '٠')
            else -> ch
        }
    }.joinToString("")

    private const val D = "0-9۰-۹٠-٩"
    private val BALANCE = Regex("""(?:مانده|موجودی)[^$D]{0,20}[$D][$D,٬.]*(?:\s*(?:ریال|تومان|rial|toman))?""", RegexOption.IGNORE_CASE)
    private val RUN = Regex("""[$D*][$D*\-\s.]*[$D*]|[$D*]""")
    private val CURRENCY_AFTER = Regex("""^\s*(?:ریال|تومان|rial|toman)""", RegexOption.IGNORE_CASE)
    private val ACCOUNT_BEFORE = Regex("""(?:کارت|حساب|card|acc(?:ount)?|شبا|iban)[^$D*]{0,12}$""", RegexOption.IGNORE_CASE)

    /**
     * The note sent to the server: balance segment removed, card/account digit runs → "****",
     * single line, then cut to 100 characters (clean first, so a cut can't expose digits).
     */
    fun cleanNote(body: String): String {
        var s = body.replace('\n', ' ').replace('\r', ' ')
        s = BALANCE.replace(s, " ")
        s = RUN.replace(s) { m ->
            val run = m.value.trimEnd()
            val trailing = m.value.substring(run.length)
            val digits = run.count { it.isDigit() }
            val after = s.substring(m.range.last + 1)
            val before = s.substring(0, m.range.first)
            val isAmount = CURRENCY_AFTER.containsMatchIn(after) && !run.contains('*') && !run.contains('-')
            val mask = !isAmount && (digits >= 5 || run.contains('*') ||
                (digits >= 3 && ACCOUNT_BEFORE.containsMatchIn(before)))
            if (mask) "****$trailing" else m.value
        }
        s = Regex("""\*{4}(?:[\s\-.]*\*{4})+""").replace(s, "****")
        s = Regex("""\s*[،,]\s*(?=[،,]|$)""").replace(s, "")
        s = SPACES.replace(s, " ").trim()
        return s.take(100)
    }

    /**
     * v5 → v6. v5 kept one phrase (KEY_PHRASE); an empty phrase meant "every SMS with an amount".
     * Returns null when the keyword list already exists.
     */
    fun migrate(existingJson: String?, v5PhraseStored: Boolean, v5Phrase: String?): Migration? {
        if (existingJson != null && fromJson(existingJson).isNotEmpty()) return null
        if (!v5PhraseStored) return Migration(listOf(DEFAULT), false)
        val p = clean(v5Phrase ?: "")
        return if (normalize(p).isEmpty()) Migration(listOf(DEFAULT), true) else Migration(listOf(p), false)
    }

    fun toJson(list: List<String>): String = JSONArray(list).toString()

    fun fromJson(json: String?): List<String> {
        if (json.isNullOrBlank()) return emptyList()
        return runCatching {
            val a = JSONArray(json)
            (0 until a.length()).map { a.getString(it) }.filter { normalize(it).isNotEmpty() }
        }.getOrDefault(emptyList())
    }
}
