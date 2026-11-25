package app.myinventory

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LearnedMerchantsTest {
    @Test fun parsesItemsAndSkipsInvalidRows() {
        val payload = JSONObject().put(
            "items",
            JSONArray()
                .put(
                    JSONObject()
                        .put("id", 7)
                        .put("merchant_label", "اسنپ")
                        .put("parent_name", "حمل‌ونقل")
                        .put("category_name", "تاکسی و اسنپ")
                )
                .put(JSONObject().put("id", 0).put("merchant_label", "bad"))
                .put(JSONObject().put("id", 9).put("merchant_label", "   "))
        )
        val rows = LearnedMerchants.parseList(payload)
        assertEquals(1, rows.size)
        assertEquals(7L, rows[0].id)
        assertEquals("اسنپ", rows[0].label)
        assertEquals("حمل‌ونقل › تاکسی و اسنپ", rows[0].subtitle())
        assertEquals("/api/merchant-categories/7", LearnedMerchants.deletePath(rows[0].id))
    }

    @Test fun emptyOrNullReturnsEmptyList() {
        assertTrue(LearnedMerchants.parseList(null).isEmpty())
        assertTrue(LearnedMerchants.parseList(JSONObject()).isEmpty())
    }
}
