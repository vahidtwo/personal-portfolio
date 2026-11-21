package app.myinventory.ui.format

import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation

const val MASK = "••••••"           // one glyph everywhere (web portfolio mask is "******"; salary is "••••••")
private const val FA = "۰۱۲۳۴۵۶۷۸۹"
private const val THOUSANDS = '٬'   // U+066C
private const val DECIMAL = '٫'     // U+066B

fun faDigits(s: String) = buildString { s.forEach { append(if (it in '0'..'9') FA[it - '0'] else it) } }

/** 2500000 → «۲٬۵۰۰٬۰۰۰». Negative uses U+2212 «−». */
fun faMoney(v: Long): String {
    val g = "%,d".format(kotlin.math.abs(v)).replace(',', THOUSANDS)
    return (if (v < 0) "−" else "") + faDigits(g)
}

/** Input normaliser (same rules as number-format.js normalizeNumberText): Persian/Arabic digits → Latin,
 *  ٬ , ، dropped, ٫ or . is the decimal point. Returns null when ambiguous. */
fun normalizeNumber(raw: String): String? {
    val t = raw.map { c ->
        when (c) { in '۰'..'۹' -> '0' + (c - '۰'); in '٠'..'٩' -> '0' + (c - '٠'); DECIMAL -> '.'; '−' -> '-'; else -> c }
    }.filterNot { it.isWhitespace() || it == '\u200c' || it == '\u200f' || it == '\u200e' }.joinToString("")
    if (t.count { it == '.' } > 1) return null
    val cleaned = t.replace(",", "").replace("$THOUSANDS", "").replace("،", "")
    return cleaned.takeIf { it.isEmpty() || Regex("^[+-]?(\\d+\\.?\\d*|\\.\\d+)$").matches(it) }
}

/** Amount field: the stored text is Latin digits only («2500000»); the field shows «۲٬۵۰۰٬۰۰۰».
 *  Use with KeyboardType.Number and filter input through normalizeNumber(). */
object AmountVisualTransformation : VisualTransformation {
    override fun filter(text: AnnotatedString): TransformedText {
        val raw = text.text
        val out = StringBuilder()
        val map = IntArray(raw.length + 1)
        for (i in raw.indices) {
            map[i] = out.length
            out.append(FA[raw[i] - '0'])
            val left = raw.length - i - 1
            if (left > 0 && left % 3 == 0) out.append(THOUSANDS)
        }
        map[raw.length] = out.length
        return TransformedText(AnnotatedString(out.toString()), object : OffsetMapping {
            override fun originalToTransformed(offset: Int) = map[offset.coerceIn(0, raw.length)]
            override fun transformedToOriginal(offset: Int): Int {
                for (i in 0..raw.length) if (map[i] >= offset) return i
                return raw.length
            }
        })
    }
}

/** Lock time from the server's retry_after (seconds). Alert: exact; button: short so it never wraps at 360dp. */
fun lockAlertTime(seconds: Int): String {
    val m = maxOf(1, (seconds + 59) / 60)
    return if (m < 60) "${faDigits("$m")} دقیقهٔ" else {
        val h = m / 60; val r = m % 60
        if (r == 0) "${faDigits("$h")} ساعت" else "${faDigits("$h")} ساعت و ${faDigits("$r")} دقیقهٔ"
    }
}
fun lockButtonLabel(seconds: Int): String {
    val m = maxOf(1, (seconds + 59) / 60)
    return if (m < 60) "دوباره امتحان کنید، ${faDigits("$m")} دقیقهٔ دیگر"
    else "دوباره امتحان کنید، حدود ${faDigits("${(m + 30) / 60}")} ساعت دیگر"
}
