package app.myinventory

import org.json.JSONArray
import org.json.JSONObject

/**
 * One decision per received SMS (pure, unit-tested): what to send to the server, or null.
 *
 * Skipped: one-time-password / code messages and every money-in SMS (plus sign, «واریز», ...).
 * Only a MINUS-signed amount is ever a spend. Accepted when
 *  A) auto-detect finds exactly one minus amount and the SMS has a «مانده» line, or
 *  C) the sender has a saved template that matches and the matched amount carries a minus sign, or
 *  B) the SMS contains one of the user's keywords AND auto-detect finds exactly one minus amount
 *     (no «مانده» line needed). The keyword list is an extra filter, never a way around the minus rule.
 * Amounts are rial / 10 unless the SMS labels them «تومان». The server gets only the toman amount and the
 * masked note.
 */
object SmsDecision {
    enum class Path { AUTO, TEMPLATE, KEYWORD }

    data class Spend(val amountToman: String, val note: String, val path: Path)

    fun decide(
        body: String,
        sender: String,
        keywords: List<String>,
        templates: List<SmsParser.Template> = emptyList(),
    ): Spend? {
        if (body.isBlank() || SmsParser.isOtp(body) || SmsParser.isMoneyIn(body)) return null
        val toman = autoAmount(body)?.let { it to Path.AUTO }
            ?: templateAmount(body, sender, templates)?.let { it to Path.TEMPLATE }
            ?: keywordAmount(body, keywords)?.let { it to Path.KEYWORD }
            ?: return null
        return Spend(toman.first.toString(), SmsKeywords.cleanNote(body), toman.second)
    }

    private fun autoAmount(body: String): Long? {
        if (!SmsParser.hasBalanceLine(body)) return null
        return SmsParser.autoDetect(body)?.amountToman?.let { -it }
    }

    private fun templateAmount(body: String, sender: String, templates: List<SmsParser.Template>): Long? =
        SmsParser.matchTemplate(body, sender, templates)?.amountToman?.let { -it }

    private fun keywordAmount(body: String, keywords: List<String>): Long? {
        if (!SmsKeywords.matchesAny(body, keywords)) return null
        return SmsParser.autoDetect(body)?.amountToman?.let { -it }
    }

    fun templatesToJson(list: List<SmsParser.Template>): String = JSONArray(list.map { t ->
        JSONObject().apply {
            put("sender", t.sender); put("sample", t.sample)
            put("amountStart", t.amountStart); put("amountEnd", t.amountEnd)
            if (t.out != null) put("out", t.out)
        }
    }).toString()

    fun templatesFromJson(json: String?): List<SmsParser.Template> {
        if (json.isNullOrBlank()) return emptyList()
        return runCatching {
            val a = JSONArray(json)
            (0 until a.length()).mapNotNull { i ->
                runCatching {
                    val o = a.getJSONObject(i)
                    SmsParser.Template(
                        o.getString("sender"), o.getString("sample"),
                        o.getInt("amountStart"), o.getInt("amountEnd"),
                        if (o.has("out")) o.getBoolean("out") else null,
                    )
                }.getOrNull()
            }
        }.getOrDefault(emptyList())
    }
}
