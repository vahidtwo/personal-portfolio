package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationTargetTest {
    @Test fun targetsAreTheDailySpendPageMarkedForTheWorker() {
        assertEquals("/dashboard?tab=daily&src=notification", NotificationTarget.DAILY)
        assertEquals("/dashboard?tab=daily&add=1&src=notification", NotificationTarget.ADD)
        assertEquals(NotificationTarget.DAILY, NotificationTarget.safePath(NotificationTarget.DAILY))
        assertEquals(NotificationTarget.ADD, NotificationTarget.safePath(NotificationTarget.ADD))
    }

    @Test fun onlySameOriginPaths() {
        assertNull(NotificationTarget.safePath(null))
        assertNull(NotificationTarget.safePath(""))
        assertNull(NotificationTarget.safePath("https://evil.example/x"))
        assertNull(NotificationTarget.safePath("//evil.example/x"))
        assertNull(NotificationTarget.safePath("/\\evil.example"))
        assertNull(NotificationTarget.safePath("javascript:alert(1)"))
        assertNull(NotificationTarget.safePath("/dashboard\n?x"))
    }

    @Test fun coldStartOpenAndLoggedOutWaitsForLogin() {
        assertEquals(NotificationTarget.Action.OPEN, NotificationTarget.action(NotificationTarget.DAILY, signedIn = true))
        assertEquals(NotificationTarget.Action.AFTER_LOGIN, NotificationTarget.action(NotificationTarget.DAILY, signedIn = false))
        assertEquals(NotificationTarget.Action.NONE, NotificationTarget.action(null, signedIn = true))
    }

    @Test fun alreadyOpenAppGetsTheIntent() {
        val newTask = 0x10000000
        val clearTop = 0x04000000
        val singleTop = 0x20000000
        assertTrue(NotificationTarget.FLAGS and newTask != 0)
        assertTrue(NotificationTarget.FLAGS and clearTop != 0)
        assertTrue(NotificationTarget.FLAGS and singleTop != 0)
    }
}
