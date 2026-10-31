package app.myinventory

import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MainFrameErrorsTest {
    private val dash = "https://daraiito.ir/dashboard"

    @Test fun offlineColdStartServedBySwIsIgnored() {
        val g = MainFrameErrors()
        g.started(dash)
        assertTrue(g.holdNetworkError(dash, false)) // error reported before the SW's page commits
        g.committed(dash)
        assertTrue(g.isPendingFor(dash))
        assertTrue(g.resolve("\"1\""))
        assertNull(g.pending)
    }

    @Test fun realFailureStillShowsErrorScreen() {
        val g = MainFrameErrors()
        g.started(dash)
        assertTrue(g.holdNetworkError(dash, false))
        assertFalse(g.resolve("\"0\"")) // no commit, not our page
        g.started(dash); g.holdNetworkError(dash, false); g.committed(dash)
        assertFalse(g.resolve("\"0\"")) // Chromium error page committed: JS says not ours
        g.started(dash); g.holdNetworkError(dash, false); g.committed(dash)
        assertFalse(g.resolve(null)) // JS failed
        g.started(dash); g.holdNetworkError(dash, false)
        assertFalse(g.resolve("\"1\"")) // never committed
    }

    @Test fun offlinePageCountsAsServedSoMarkerFallbackRuns() {
        val js = MainFrameErrors.SERVED_JS
        assertTrue(js.contains("meta[name=\"x-offline\"]") && js.contains("location.protocol==='https:'"))
    }

    @Test fun notHeldDuringHostMoveOrForLocalPages() {
        val g = MainFrameErrors()
        assertFalse(g.holdNetworkError(dash, true))
        assertFalse(g.holdNetworkError("file:///android_asset/www/setup.html", false))
        assertFalse(g.holdNetworkError(null, false))
    }

    @Test fun httpErrorOnlyHeldAfterCommit() {
        val g = MainFrameErrors()
        g.started(dash)
        assertFalse(g.holdHttpError(dash, false)) // 5xx before any page: error screen at once
        g.committed("$dash#x")
        assertTrue(g.holdHttpError(dash, false))
        assertFalse(g.holdHttpError(dash, true))
    }

    @Test fun newNavigationForgetsOldCommit() {
        val g = MainFrameErrors()
        g.started(dash); g.committed(dash)
        g.started("https://daraiito.ir/login")
        assertFalse(g.wasCommitted(dash))
        g.started("file:///android_asset/www/setup_error.html")
        assertNull(g.pending)
        assertTrue(g.resolve(null)) // nothing pending = nothing to show
    }
}
