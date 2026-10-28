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

    private val signedIn = "inventory_session=abc; inventory_signed_in=1"
    private val anonymous = "inventory_session=anon-csrf-only"

    @Test fun smsTargetPrefersNewSessionThenOld() {
        val both = mapOf(new to signedIn, old to "$signedIn; x=old")
        assertEquals(new to signedIn, ServerAddress.smsTarget(new) { both[it] })
        assertEquals(old to "$signedIn; x=old", ServerAddress.smsTarget(new) { mapOf(old to "$signedIn; x=old")[it] })
        assertNull(ServerAddress.smsTarget(new) { null })
        assertNull(ServerAddress.smsTarget(new) { "" })
        assertNull(ServerAddress.smsTarget("https://my.server.example") { mapOf(old to signedIn)[it] })
        assertEquals(old to signedIn, ServerAddress.smsTarget(old) { mapOf(old to signedIn)[it] })
    }

    // Fix 3: an anonymous cookie (inventory_session from visiting /auth) is not a login.
    @Test fun anonymousCookieIsNotASession() {
        assertFalse(ServerAddress.hasSignedInSession(anonymous))
        assertFalse(ServerAddress.hasSignedInSession("inventory_signed_in=1"))
        assertFalse(ServerAddress.hasSignedInSession("inventory_session=; inventory_signed_in=1"))
        assertFalse(ServerAddress.hasSignedInSession("inventory_session=abc; inventory_signed_in=0"))
        assertFalse(ServerAddress.hasSignedInSession("other=1; inventory_signed_in_x=1; inventory_session=a"))
        assertFalse(ServerAddress.hasSignedInSession(null))
        assertTrue(ServerAddress.hasSignedInSession(signedIn))
        assertTrue(ServerAddress.hasSignedInSession("a=b;inventory_signed_in=1;  inventory_session=x=y"))
        // new host anonymous, old host signed in -> old; both anonymous -> nobody
        assertEquals(old to signedIn, ServerAddress.smsTarget(new) { mapOf(new to anonymous, old to signedIn)[it] })
        assertNull(ServerAddress.smsTarget(new) { mapOf(new to anonymous, old to anonymous)[it] })
    }

    // Fix 4: no session / 401 -> the login notice; never a silent drop.
    @Test fun smsOutcome() {
        assertEquals(ServerAddress.SmsOutcome.SAVED, ServerAddress.smsOutcome(200))
        assertEquals(ServerAddress.SmsOutcome.SAVED, ServerAddress.smsOutcome(201))
        assertEquals(ServerAddress.SmsOutcome.LOGIN_NEEDED, ServerAddress.smsOutcome(401))
        assertEquals(ServerAddress.SmsOutcome.LOGIN_NEEDED, ServerAddress.smsOutcome(403))
        assertEquals(ServerAddress.SmsOutcome.FAILED, ServerAddress.smsOutcome(303))
        assertEquals(ServerAddress.SmsOutcome.FAILED, ServerAddress.smsOutcome(500))
        assertEquals(ServerAddress.SmsOutcome.FAILED, ServerAddress.smsOutcome(null))
    }

    // Fix 1: hidden amounts stay hidden.
    @Test fun privacyCarriedOverFailSafe() {
        assertTrue(ServerAddress.hideAfterMove("\"1\""))
        assertFalse(ServerAddress.hideAfterMove("null"))
        assertFalse(ServerAddress.hideAfterMove("\"0\""))
        assertTrue(ServerAddress.hideAfterMove(null))      // timeout / old host unreachable
        assertTrue(ServerAddress.hideAfterMove("\"err\"")) // localStorage threw
        assertTrue(ServerAddress.hideAfterMove(""))
        assertEquals("https://daraiito.ir/dashboard#hide=1", ServerAddress.moveTarget(true))
        assertEquals("https://daraiito.ir/dashboard", ServerAddress.moveTarget(false))
    }

    // Fix 2: after a fallback the move is retried on a later launch, never twice in one launch, capped.
    @Test fun moveRetriedAfterFallbackWithoutLoop() {
        // fallback cleared host_migrated; next cold launch:
        assertTrue(ServerAddress.shouldMigrate(old, alreadyMigrated = false, fallbackCount = 1, triedThisLaunch = false))
        // same launch: no second try
        assertFalse(ServerAddress.shouldMigrate(old, alreadyMigrated = false, fallbackCount = 1, triedThisLaunch = true))
        assertTrue(ServerAddress.shouldMigrate(old, false, ServerAddress.MAX_FALLBACKS - 1, false))
        assertFalse(ServerAddress.shouldMigrate(old, false, ServerAddress.MAX_FALLBACKS, false))
        // fallback at most once per launch
        assertTrue(ServerAddress.shouldFallBack(new, true, false, "$new/dashboard"))
        assertFalse(ServerAddress.shouldFallBack(new, true, true, "$new/dashboard"))
        // simulated launches: move, fail, fall back, ... stops after MAX_FALLBACKS
        var migrated = false; var count = 0; var saved = old; var moves = 0
        repeat(10) {
            var tried = false; var fellBack = false
            if (ServerAddress.shouldMigrate(saved, migrated, count, tried)) { tried = true; saved = new; migrated = true; moves++ }
            if (ServerAddress.shouldFallBack(saved, migrated, fellBack, "$new/dashboard")) { fellBack = true; saved = old; migrated = false; count++ }
        }
        assertEquals(ServerAddress.MAX_FALLBACKS, moves)
        assertEquals(old, saved)
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
