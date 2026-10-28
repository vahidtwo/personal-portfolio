package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class HostMoveTest {
    private val old = "https://portfolio.vahidtwo.ir"
    private val new = "https://daraiito.ir"

    @Test fun defaultIsNewHost() {
        assertEquals(new, ServerAddress.DEFAULT)
        assertEquals(old, ServerAddress.OLD_DEFAULT)
        assertEquals(new, ServerAddress.normalizeOrDefault(""))
    }

    @Test fun migratesOldDefaultVariants() {
        for (raw in listOf(old, "$old/", "http://portfolio.vahidtwo.ir", "HTTPS://Portfolio.VahidTwo.IR", "$old/dashboard", " $old ")) {
            assertTrue(raw, ServerAddress.shouldMigrate(raw, alreadyMigrated = false))
        }
    }

    @Test fun runsOnce() {
        assertFalse(ServerAddress.shouldMigrate(old, alreadyMigrated = true))
        assertFalse(ServerAddress.shouldMigrate(new, alreadyMigrated = false))
    }

    @Test fun customAndEmptyNotMigrated() {
        for (raw in listOf(null, "", "https://my.server.example", "https://portfolio.vahidtwo.ir:8443",
            "https://portfolio.vahidtwo.ir.evil.example", "https://10.0.2.2")) {
            assertFalse(raw.toString(), ServerAddress.shouldMigrate(raw, alreadyMigrated = false))
        }
    }

    @Test fun healthCheck() {
        assertTrue(ServerAddress.isHealthOk(200, "{\"ok\":true}"))
        assertTrue(ServerAddress.isHealthOk(200, "{\"ok\": true}"))
        assertFalse(ServerAddress.isHealthOk(200, "{\"ok\":false}"))
        assertFalse(ServerAddress.isHealthOk(301, "{\"ok\":true}"))
        assertFalse(ServerAddress.isHealthOk(200, "<html>"))
        assertFalse(ServerAddress.isHealthOk(200, null))
    }

    @Test fun bothHostsAllowed() {
        for (saved in listOf(old, new)) {
            assertTrue(ServerAddress.isAllowedRemote("https", "daraiito.ir", saved))
            assertTrue(ServerAddress.isAllowedRemote("https", "portfolio.vahidtwo.ir", saved))
            assertTrue(ServerAddress.isAllowedRemote("https", "DARAIITO.IR", saved))
        }
    }

    @Test fun lookalikesAndHttpBlocked() {
        for (host in listOf("portfolio.vahidtwo.ir.evil.example", "evil-daraiito.ir", "www.daraiito.ir.evil.example",
            "daraiito.ir.evil.example", "evil.example", "vahidtwo.ir", "")) {
            assertFalse(host, ServerAddress.isAllowedRemote("https", host, new))
        }
        assertFalse(ServerAddress.isAllowedRemote("http", "daraiito.ir", new))
        assertFalse(ServerAddress.isAllowedRemote("http", "portfolio.vahidtwo.ir", old))
        assertFalse(ServerAddress.isAllowedRemote(null, "daraiito.ir", new))
    }

    @Test fun customHostStillWorks() {
        assertTrue(ServerAddress.isAllowedRemote("https", "my.server.example", "https://my.server.example"))
        assertFalse(ServerAddress.isAllowedRemote("https", "other.example", "https://my.server.example"))
        assertTrue(ServerAddress.isAllowedRemote("https", "anything.example", null)) // setup page, like v8
    }

    @Test fun fallbackOnlyOnceAndOnlyAfterMove() {
        assertTrue(ServerAddress.shouldFallBack(new, true, false, "$new/dashboard"))
        assertFalse(ServerAddress.shouldFallBack(new, true, true, "$new/dashboard"))
        assertFalse(ServerAddress.shouldFallBack(new, false, false, "$new/dashboard"))
        assertFalse(ServerAddress.shouldFallBack(old, true, false, "$old/dashboard"))
        assertFalse(ServerAddress.shouldFallBack(new, true, false, null))
        assertFalse(ServerAddress.shouldFallBack(new, true, false, "https://evil.example/"))
    }

    @Test fun smsTargetPrefersNewCookieThenOld() {
        val both = mapOf(new to "s=new", old to "s=old")
        assertEquals(new to "s=new", ServerAddress.smsTarget(new) { both[it] })
        assertEquals(old to "s=old", ServerAddress.smsTarget(new) { mapOf(old to "s=old")[it] })
        assertNull(ServerAddress.smsTarget(new) { null })
        assertNull(ServerAddress.smsTarget(new) { "" })
        assertNull(ServerAddress.smsTarget("https://my.server.example") { mapOf(old to "s=old")[it] })
        assertEquals(old to "s=old", ServerAddress.smsTarget(old) { both[it] })
    }

    @Test fun updaterWorksOnBothHosts() {
        for (base in listOf(old, new)) {
            assertEquals("$base/download/my-inventory.apk", UpdateCheck.resolveDownloadUrl(base, "/download/my-inventory.apk"))
            assertTrue(UpdateCheck.isEligiblePage("$base/dashboard", base))
        }
        assertNull(UpdateCheck.resolveDownloadUrl(new, "https://portfolio.vahidtwo.ir/download/my-inventory.apk"))
        assertFalse(UpdateCheck.isEligiblePage("$old/dashboard", new))
    }
}
