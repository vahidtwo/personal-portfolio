package app.myinventory

import app.myinventory.settings.SettingsModel
import app.myinventory.ui.components.amountDigits
import app.myinventory.ui.format.faDigits
import app.myinventory.ui.format.faMoney
import app.myinventory.ui.format.normalizeNumber
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NativeSettingsTest {
    @Test fun formatHelpers() {
        assertEquals("۱۲.۱.۶", faDigits("12.1.6"))
        assertEquals("۲٬۵۰۰٬۰۰۰", faMoney(2_500_000))
        assertEquals("−۱٬۰۰۰", faMoney(-1000))
        assertEquals("2500000", normalizeNumber("۲٬۵۰۰٬۰۰۰"))
        assertNull(normalizeNumber("1.2.3"))
    }

    @Test fun amountInputKeepsDigitsOnly() {
        assertEquals("48000000", amountDigits("۴۸٬۰۰۰٬۰۰۰"))
        assertEquals("120", amountDigits("12a0 تومان"))
        assertEquals("0", amountDigits("000"))
        assertEquals("", amountDigits("abc"))
        assertEquals(15, amountDigits("9".repeat(20)).length)
    }

    @Test fun parsesSettingsWithoutSalary() {
        val d = SettingsModel.parse(JSONObject(
            """{"account":{"full_name":"سارا","username":"sara_demo","mobile":""},"has_salary":true,"is_admin":false}""",
        ))!!
        assertEquals("sara_demo", d.username)
        assertFalse(d.isAdmin)
        assertNull(SettingsModel.parse(JSONObject("{}")))
    }

    @Test fun writeResultReadsServerErrors() {
        val bad = SettingsModel.writeResult(422, JSONObject("""{"ok":false,"errors":{"username":"این نام کاربری قبلاً ثبت شده"}}"""))
        assertFalse(bad.ok)
        assertEquals("این نام کاربری قبلاً ثبت شده", bad.errors["username"])
        val good = SettingsModel.writeResult(200, JSONObject("""{"ok":true,"title":"حساب ذخیره شد","detail":"x"}"""))
        assertTrue(good.ok)
        assertEquals("حساب ذخیره شد", good.title)
    }

    @Test fun salaryLabelSplitsNumberAndUnit() {
        assertEquals("۴۵٬۰۰۰٬۰۰۰" to "تومان", SettingsModel.salaryParts("۴۵٬۰۰۰٬۰۰۰ تومان"))
        assertNull(SettingsModel.salaryParts("—"))
        assertNull(SettingsModel.salaryParts(""))
        assertTrue(SettingsModel.salaryIsNone("۰"))
        assertFalse(SettingsModel.salaryIsNone("۴۵٬۰۰۰٬۰۰۰"))
        assertFalse(SettingsModel.salaryIsNone("۱۰"))
    }

    @Test fun amountWordsGuardTypos() {
        assertEquals("چهل و هشت میلیون تومان", app.myinventory.ui.format.amountWordsLine("48000000"))
        assertEquals("هزار و پانصد تومان", app.myinventory.ui.format.amountWordsLine("1500"))
        assertEquals("نه تریلیون و نهصد و نود و نه میلیارد و نهصد و نود و نه میلیون و نهصد و نود و نه هزار و نهصد و نود و نه تومان",
            app.myinventory.ui.format.amountWordsLine("9999999999999"))
        assertNull(app.myinventory.ui.format.amountWordsLine(""))
    }

    @Test fun versionUsesPersianDigitsAndSeparator() {
        assertEquals("۱۲٫۱٫۷", SettingsModel.versionLabel("12.1.7", ::faDigits))
    }

    @Test fun smallRules() {
        assertEquals("س", SettingsModel.avatarLetter("سارا نمونه", "sara"))
        assertEquals("S", SettingsModel.avatarLetter(" ", "sara"))
        assertTrue(SettingsModel.needsCurrentPassword("sara", "sara2"))
        assertFalse(SettingsModel.needsCurrentPassword("sara", " Sara "))
        assertEquals("روشن، ۲ کلمه", SettingsModel.smsTrailing(true, 2, ::faDigits))
        assertEquals("خاموش", SettingsModel.smsTrailing(false, 2, ::faDigits))
    }

    @Test fun themeChoiceDefaultsToAuto() {
        assertEquals(AppTheme.AUTO, AppTheme.normalize(null))
        assertEquals(AppTheme.AUTO, AppTheme.normalize("blue"))
        assertEquals(AppTheme.DARK, AppTheme.normalize("dark"))
    }
}
