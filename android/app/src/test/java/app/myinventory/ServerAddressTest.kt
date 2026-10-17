package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerAddressTest {
    @Test fun defaultIsKept() =
        assertEquals("https://portfolio.vahidtwo.ir", ServerAddress.normalize("https://portfolio.vahidtwo.ir"))

    @Test fun trailingSlashAndPathAreDropped() =
        assertEquals("https://portfolio.vahidtwo.ir", ServerAddress.normalize("  https://portfolio.vahidtwo.ir/dashboard/ "))

    @Test fun noSchemeGetsHttps() =
        assertEquals("https://portfolio.vahidtwo.ir", ServerAddress.normalize("portfolio.vahidtwo.ir"))

    @Test fun noSchemeWithPort() =
        assertEquals("https://example.com:8443", ServerAddress.normalize("example.com:8443"))

    @Test fun httpIsUpgradedToHttps() =
        assertEquals("https://portfolio.vahidtwo.ir", ServerAddress.normalize("http://portfolio.vahidtwo.ir"))

    @Test fun upperCaseSchemeAndHost() =
        assertEquals("https://portfolio.vahidtwo.ir", ServerAddress.normalize("HTTPS://Portfolio.VahidTwo.ir"))

    @Test fun emptyIsRejected() = assertNull(ServerAddress.normalize("   "))

    @Test fun emptyFallsBackToDefault() =
        assertEquals(ServerAddress.DEFAULT, ServerAddress.normalizeOrDefault(""))

    @Test fun otherSchemesAreRejected() {
        assertNull(ServerAddress.normalize("ftp://example.com"))
        assertNull(ServerAddress.normalize("javascript:alert(1)"))
        assertNull(ServerAddress.normalize("file:///etc/passwd"))
    }

    @Test fun schemeOnlyIsRejected() {
        assertNull(ServerAddress.normalize("https://"))
        assertNull(ServerAddress.normalize("http://"))
    }

    @Test fun garbageIsRejected() = assertNull(ServerAddress.normalize("not a url"))
}
