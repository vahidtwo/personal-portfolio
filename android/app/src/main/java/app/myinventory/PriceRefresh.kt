package app.myinventory

import org.json.JSONObject

/** Native home «به‌روزرسانی»: asks the server to fetch market prices now, then reads the home again. */
object PriceRefresh {
    const val PATH = "/api/home/refresh-prices"
    /** The server waits on chande (and the car value) before it answers. */
    const val TIMEOUT_MS = 90_000
    const val BUSY_LABEL = "در حال به‌روزرسانی…"
    const val OFFLINE_MESSAGE = "اتصال برقرار نشد؛ دوباره امتحان کنید"
    const val FAILED_MESSAGE = "به‌روزرسانی انجام نشد؛ دوباره امتحان کنید"

    enum class Next { RELOAD_HOME, SIGN_OUT }

    data class Outcome(val next: Next, val message: String)

    fun outcome(status: Int?, json: JSONObject?): Outcome = when {
        status == null -> Outcome(Next.RELOAD_HOME, OFFLINE_MESSAGE)
        status == 401 -> Outcome(Next.SIGN_OUT, "")
        else -> Outcome(Next.RELOAD_HOME, json?.optString("message")?.takeIf { it.isNotBlank() } ?: FAILED_MESSAGE)
    }

    /** Label of the disabled button while the server's cooldown runs, or null when a refresh is allowed now. */
    fun waitLabel(price: JSONObject?): String? {
        if (price == null || price.optInt("wait_sec", 0) <= 0) return null
        return price.optString("wait_label").takeIf { it.isNotBlank() }
    }
}
