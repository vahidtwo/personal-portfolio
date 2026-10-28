package app.myinventory

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class StartupGateTest {
    @Test fun splashHeldUntilFirstPaint() {
        val g = StartupGate()
        g.created(1000)
        assertTrue(g.keepSplash(1000))
        assertTrue(g.keepSplash(2400))
        g.firstPaint(2500, "https://daraiito.ir/dashboard")
        assertFalse(g.keepSplash(2501))
        assertTrue(g.hasPainted)
    }

    @Test fun splashCappedAt2500ms() {
        val g = StartupGate()
        g.created(0)
        assertTrue(g.keepSplash(StartupGate.SPLASH_MAX_MS - 1))
        assertFalse(g.keepSplash(StartupGate.SPLASH_MAX_MS))
        assertFalse(StartupGate.shouldKeepSplash(false, 10_000))
    }

    @Test fun recreateResetsGate() {
        val g = StartupGate()
        g.created(0); g.firstPaint(10, null)
        g.created(100)
        assertTrue(g.keepSplash(150))
    }

    @Test fun revealOnlyForRealPagesNotDuringHostMoveOrError() {
        assertTrue(StartupGate.revealOnCommit("https://daraiito.ir/dashboard", false, false))
        assertTrue(StartupGate.revealOnCommit("file:///android_asset/www/setup.html", false, false))
        assertFalse(StartupGate.revealOnCommit("https://portfolio.vahidtwo.ir/health", true, false))
        assertFalse(StartupGate.revealOnCommit("https://daraiito.ir/dashboard", false, true))
        assertFalse(StartupGate.revealOnCommit("about:blank", false, false))
        assertFalse(StartupGate.revealOnCommit(null, false, false))
    }
}
