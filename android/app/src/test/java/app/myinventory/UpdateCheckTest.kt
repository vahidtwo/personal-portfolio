package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateCheckTest {
    private val base = "https://portfolio.vahidtwo.ir"

    @Test fun parsesServerResponse() {
        val info = UpdateCheck.parse(
            """{"versionCode":6,"versionName":"6.0","url":"/download/my-inventory.apk","sha256":"ab","notes":["یک","دو"]}""",
        )!!
        assertEquals(6L, info.versionCode)
        assertEquals("6.0", info.versionName)
        assertEquals("/download/my-inventory.apk", info.url)
        assertEquals(listOf("یک", "دو"), info.notes)
        assertEquals(0L, info.minRequired)
    }

    @Test fun minRequiredIsParsedButOptional() {
        assertEquals(4L, UpdateCheck.parse("""{"versionCode":6,"versionName":"6.0","url":"/a.apk","min_required":4}""")!!.minRequired)
        assertEquals(0L, UpdateCheck.parse("""{"versionCode":6,"versionName":"6.0","url":"/a.apk","min_required":"x"}""")!!.minRequired)
    }

    @Test fun minRequiredDoesNotForceANotice() =
        // Forced updates aren't approved: «بعداً» on 6 stays quiet even if min_required is 6.
        assertFalse(UpdateCheck.shouldNotify(remoteCode = 6, installedCode = 5, dismissedCode = 6))

    @Test fun missingNotesIsOk() =
        assertEquals(emptyList<String>(), UpdateCheck.parse("""{"versionCode":6,"versionName":"6.0","url":"/a.apk"}""")!!.notes)

    @Test fun brokenOrWrongTypesAreIgnored() {
        for (body in listOf(
            null, "", "not json", "[]", "<html>502</html>",
            """{"versionCode":"6","versionName":"6.0","url":"/a.apk"}""",
            """{"versionCode":6.5,"versionName":"6.0","url":"/a.apk"}""",
            """{"versionCode":0,"versionName":"6.0","url":"/a.apk"}""",
            """{"versionCode":6,"versionName":6,"url":"/a.apk"}""",
            """{"versionCode":6,"versionName":"6.0"}""",
            """{"versionCode":6,"versionName":"6.0","url":"/a.apk","notes":"x"}""",
        )) assertNull(body, UpdateCheck.parse(body))
    }

    @Test fun relativeUrlResolvesAgainstBase() =
        assertEquals("$base/download/my-inventory.apk", UpdateCheck.resolveDownloadUrl(base, "/download/my-inventory.apk"))

    @Test fun absoluteSameHostHttpsIsAllowed() =
        assertEquals("$base/x.apk", UpdateCheck.resolveDownloadUrl(base, "https://portfolio.vahidtwo.ir/x.apk"))

    @Test fun otherHostsAndSchemesAreRejected() {
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
        )) assertNull(url, UpdateCheck.resolveDownloadUrl(base, url))
    }

    @Test fun notifyOnlyForNewerUndismissedBuild() {
        assertTrue(UpdateCheck.shouldNotify(remoteCode = 6, installedCode = 5, dismissedCode = 0))
        assertFalse(UpdateCheck.shouldNotify(remoteCode = 5, installedCode = 5, dismissedCode = 0))
        assertFalse(UpdateCheck.shouldNotify(remoteCode = 4, installedCode = 5, dismissedCode = 0))
        // «بعداً» on 6 keeps quiet for 6, but 7 shows again
        assertFalse(UpdateCheck.shouldNotify(remoteCode = 6, installedCode = 5, dismissedCode = 6))
        assertTrue(UpdateCheck.shouldNotify(remoteCode = 7, installedCode = 5, dismissedCode = 6))
    }
}
