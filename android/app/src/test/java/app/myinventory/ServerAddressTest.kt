package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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

    @Test fun setupPageMayNavigate() = assertEquals(
        ServerAddress.BridgeAction.NAVIGATE,
        ServerAddress.bridgeAction("file:///android_asset/www/setup.html?error=connect", "https://portfolio.vahidtwo.ir"),
    )

    @Test fun remotePageSameHostOnlySaves() {
        for (page in listOf("https://portfolio.vahidtwo.ir/", "https://portfolio.vahidtwo.ir/dashboard", "https://portfolio.vahidtwo.ir/login?next=/")) {
            assertEquals(page, ServerAddress.BridgeAction.SAVE_ONLY, ServerAddress.bridgeAction(page, "https://portfolio.vahidtwo.ir"))
        }
    }

    @Test fun remotePageOtherHostIsIgnored() = assertEquals(
        ServerAddress.BridgeAction.IGNORE,
        ServerAddress.bridgeAction("https://evil.example/", "https://portfolio.vahidtwo.ir"),
    )

    @Test fun unknownPageIsIgnored() {
        assertEquals(ServerAddress.BridgeAction.IGNORE, ServerAddress.bridgeAction(null, "https://portfolio.vahidtwo.ir"))
        assertEquals(ServerAddress.BridgeAction.IGNORE, ServerAddress.bridgeAction("about:blank", "https://portfolio.vahidtwo.ir"))
        assertEquals(ServerAddress.BridgeAction.IGNORE, ServerAddress.bridgeAction("http://portfolio.vahidtwo.ir/", "https://portfolio.vahidtwo.ir"))
    }

    @Test
    fun githubOpensExternallyOnlyOverHttpsExactHost() {
        assertTrue(ServerAddress.opensExternally("https", "github.com"))
        assertTrue(ServerAddress.opensExternally("HTTPS", "GitHub.com"))
        for ((scheme, host) in listOf("http" to "github.com", "https" to "github.com.evil.example",
                "https" to "evil-github.com", "https" to "daraiito.ir", "https" to null, null to "github.com")) {
            assertFalse("$scheme $host", ServerAddress.opensExternally(scheme, host))
        }
        assertFalse(ServerAddress.isAllowedRemote("https", "github.com", "https://daraiito.ir"))
    }
}
