package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DirectFlavorTest {
    @Test fun inAppUpdatesStayOnInTheDirectBuild() {
        assertEquals("direct", BuildConfig.FLAVOR)
        assertTrue(BuildConfig.IN_APP_UPDATES)
        assertTrue(UpdateCheck.inAppUpdatesEnabled)
        assertEquals("app.myinventory", BuildConfig.APPLICATION_ID)
        assertEquals(16, BuildConfig.VERSION_CODE)
    }
}
