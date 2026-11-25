package app.myinventory

import org.json.JSONObject

data class LearnedMerchant(
    val id: Long,
    val label: String,
    val parentName: String,
    val categoryName: String,
) {
    fun subtitle(): String = "$parentName › $categoryName"
}

object LearnedMerchants {
    const val PATH_LIST = "/api/merchant-categories"
    const val TITLE = "فروشگاه‌های یادگرفته"
    const val DESC = "خرج‌های پیامکی تازه از این فروشگاه‌ها خودکار در همین دسته ثبت می‌شوند. حذف، خرج‌های قبلی را عوض نمی‌کند."
    const val EMPTY = "هنوز فروشگاهی یاد گرفته نشده. با تیک «همیشه همین دسته» در برگهٔ دسته اضافه می‌شود."
    const val SAVE_FAILED = "ذخیره نشد؛ دوباره بزنید"

    fun deletePath(id: Long): String = "$PATH_LIST/$id"

    fun parseList(json: JSONObject?): List<LearnedMerchant> {
        val items = json?.optJSONArray("items") ?: return emptyList()
        val out = ArrayList<LearnedMerchant>(items.length())
        for (i in 0 until items.length()) {
            val o = items.optJSONObject(i) ?: continue
            val id = o.optLong("id", 0L)
            val label = o.optString("merchant_label").trim()
            if (id <= 0L || label.isEmpty()) continue
            val parentName = o.optString("parent_name").trim().ifEmpty { "سایر" }
            val categoryName = o.optString("category_name").trim().ifEmpty { parentName }
            out.add(LearnedMerchant(id = id, label = label, parentName = parentName, categoryName = categoryName))
        }
        return out
    }
}
