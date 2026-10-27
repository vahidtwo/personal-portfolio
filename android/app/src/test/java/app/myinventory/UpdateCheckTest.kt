package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateCheckTest {
    private val base = "https://portfolio.vahidtwo.ir"
    private val sha = "a".repeat(64)
    private val hour = 60L * 60 * 1000
    private val t0 = 1_760_000_000_000L

    @Test fun parsesServerResponse() {
        val info = UpdateCheck.parse(
            """{"versionCode":6,"versionName":"6.0","url":"/download/my-inventory.apk","sha256":"$sha",
               "size_bytes":3287333,"cert_sha256":"${"B".repeat(64)}","notes":["یک","دو"],"min_required":0}""",
        )!!
        assertEquals(6L, info.versionCode)
        assertEquals("6.0", info.versionName)
        assertEquals("/download/my-inventory.apk", info.url)
        assertEquals(sha, info.sha256)
        assertEquals(3287333L, info.sizeBytes)
        assertEquals("b".repeat(64), info.certSha256)
        assertEquals(listOf("یک", "دو"), info.notes)
        assertEquals(0L, info.minRequired)
    }

    @Test fun missingOptionalFieldsAreOk() {
        val info = UpdateCheck.parse("""{"versionCode":6,"versionName":"6.0","url":"/a.apk"}""")!!
        assertEquals(emptyList<String>(), info.notes)
        assertNull(info.sha256)
        assertNull(info.sizeBytes)
        assertEquals(0L, info.minRequired)
    }

    @Test fun atMostFourNotes() =
        assertEquals(4, UpdateCheck.parse("""{"versionCode":6,"versionName":"6","url":"/a","notes":["1","2","3","4","5"]}""")!!.notes.size)

    @Test fun minRequiredIsParsedButOptional() {
        assertEquals(4L, UpdateCheck.parse("""{"versionCode":6,"versionName":"6.0","url":"/a.apk","min_required":4}""")!!.minRequired)
        assertEquals(0L, UpdateCheck.parse("""{"versionCode":6,"versionName":"6.0","url":"/a.apk","min_required":"x"}""")!!.minRequired)
    }

    @Test fun badShaIsDropped() =
        assertNull(UpdateCheck.parse("""{"versionCode":6,"versionName":"6","url":"/a","sha256":"xyz"}""")!!.sha256)

    @Test fun brokenOrWrongTypesAreIgnored() {
        for (body in listOf(
            null, "", "not json", "{not json", "[]", "<html>502</html>",
            """{"versionCode":"6","versionName":"6.0","url":"/a.apk"}""",
            """{"versionCode":6.5,"versionName":"6.0","url":"/a.apk"}""",
            """{"versionCode":0,"versionName":"6.0","url":"/a.apk"}""",
            """{"versionCode":6,"versionName":6,"url":"/a.apk"}""",
            """{"versionCode":6,"versionName":"6.0"}""",
            """{"versionCode":6,"versionName":"6.0","url":"/a.apk","notes":"x"}""",
        )) assertNull(body, UpdateCheck.parse(body))
    }

    // ---- URL / host validation ----

    @Test fun relativeUrlResolvesAgainstBase() =
        assertEquals("$base/download/my-inventory.apk", UpdateCheck.resolveDownloadUrl(base, "/download/my-inventory.apk"))

    @Test fun absoluteSameHostHttpsIsAllowed() =
        assertEquals("$base/x.apk", UpdateCheck.resolveDownloadUrl(base, "https://portfolio.vahidtwo.ir/x.apk"))

    @Test fun releaseRejectsOtherHostsAndSchemes() {
        for (url in listOf(
            "https://evil.example/x.apk",
            "http://portfolio.vahidtwo.ir/x.apk",
            "//evil.example/x.apk",
            "https://portfolio.vahidtwo.ir.evil.example/x.apk",
            "https://portfolio.vahidtwo.ir:8443/x.apk",
            "javascript:alert(1)",
            "file:///sdcard/x.apk",
            "intent://x#Intent;end",
            "ht tp://bad",
            "http://10.0.2.2:8765/x.apk",
        )) assertNull(url, UpdateCheck.resolveDownloadUrl(base, url))
    }

    @Test fun releaseNeverAcceptsAnHttpBase() =
        assertNull(UpdateCheck.resolveDownloadUrl("http://portfolio.vahidtwo.ir", "/x.apk"))

    @Test fun qaAllowsHttpOnlyForItsTestHost() {
        val qa = "http://10.0.2.2:8765"
        assertEquals("$qa/download/my-inventory.apk", UpdateCheck.resolveDownloadUrl(qa, "/download/my-inventory.apk", "10.0.2.2"))
        assertNull(UpdateCheck.resolveDownloadUrl(qa, "http://example.com/x.apk", "10.0.2.2"))
        assertNull(UpdateCheck.resolveDownloadUrl(qa, "https://evil.example/x.apk", "10.0.2.2"))
        assertNull(UpdateCheck.resolveDownloadUrl(qa, "http://10.0.2.2:9999/x.apk", "10.0.2.2"))
        assertNull(UpdateCheck.resolveDownloadUrl("http://example.com", "/x.apk", "10.0.2.2"))
        // without the QA allowance the same test server is rejected
        assertNull(UpdateCheck.resolveDownloadUrl(qa, "/download/my-inventory.apk"))
    }

    // ---- «بعداً» with an injected clock ----

    @Test fun notifyOnlyForNewerBuild() {
        assertTrue(UpdateCheck.shouldNotify(6, 5, 0, 0, t0))
        assertFalse(UpdateCheck.shouldNotify(5, 5, 0, 0, t0))
        assertFalse(UpdateCheck.shouldNotify(4, 5, 0, 0, t0))
    }

    @Test fun laterSnoozesFor24Hours() {
        assertFalse(UpdateCheck.shouldNotify(6, 5, dismissedCode = 6, dismissedAtMs = t0, nowMs = t0 + 1))
        assertFalse(UpdateCheck.shouldNotify(6, 5, 6, t0, t0 + 23 * hour + 59 * 60_000))
        assertTrue(UpdateCheck.shouldNotify(6, 5, 6, t0, t0 + 24 * hour))
        assertTrue(UpdateCheck.shouldNotify(6, 5, 6, t0, t0 + 72 * hour))
    }

    @Test fun higherVersionBreaksTheSnooze() =
        assertTrue(UpdateCheck.shouldNotify(7, 5, dismissedCode = 6, dismissedAtMs = t0, nowMs = t0 + hour))

    @Test fun clockMovedBackDoesNotSilenceForever() =
        assertTrue(UpdateCheck.shouldNotify(6, 5, 6, dismissedAtMs = t0, nowMs = t0 - hour))

    @Test fun minRequiredDoesNotForceANotice() {
        val info = UpdateCheck.parse("""{"versionCode":6,"versionName":"6","url":"/a","min_required":6}""")!!
        assertFalse(UpdateCheck.shouldNotify(info.versionCode, 5, 6, t0, t0 + hour))
    }

    // ---- where the notice may appear ----

    @Test fun eligiblePages() {
        assertTrue(UpdateCheck.isEligiblePage("$base/dashboard", base))
        assertTrue(UpdateCheck.isEligiblePage("$base/dashboard/", base))
        assertTrue(UpdateCheck.isEligiblePage("$base/dashboard?tab=daily", base))
        for (page in listOf(
            "$base/profile", "$base/profile?tab=debts", "$base/assets", "$base/spends", "$base/dashboard/x",
            "$base/auth", "$base/auth?back=1", "$base/logout", "$base/dashboardx",
            "$base/", base, "$base/login", "$base/login?next=/", "$base/register",
            "file:///android_asset/www/setup.html", "file:///android_asset/www/setup.html?error=connect",
            "https://evil.example/dashboard", "http://portfolio.vahidtwo.ir/dashboard", null,
        )) assertFalse(page.toString(), UpdateCheck.isEligiblePage(page, base))
        assertFalse(UpdateCheck.isEligiblePage("$base/dashboard", null))
    }

    // ---- Persian formatting ----

    @Test fun persianFormatting() {
        assertEquals("حدود ۳ مگابایت", UpdateCheck.sizeAbout(3_287_333))
        assertEquals("حدود ۱ مگابایت", UpdateCheck.sizeAbout(100_000))
        assertNull(UpdateCheck.sizeAbout(null))
        assertEquals("۶۲٪", UpdateCheck.percent(62, 100))
        assertEquals("۱٫۹ از ۳٫۱ مگابایت", UpdateCheck.progressMb(1_992_294, 3_250_586))
        assertEquals("۵", UpdateCheck.fa("5"))
    }
}
