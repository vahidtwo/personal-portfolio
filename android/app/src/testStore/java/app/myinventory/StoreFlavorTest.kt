package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class StoreFlavorTest {
    @Test fun inAppUpdatesAreDisabledInTheStoreBuild() {
        assertEquals("store", BuildConfig.FLAVOR)
        assertFalse(BuildConfig.IN_APP_UPDATES)
        assertFalse(UpdateCheck.inAppUpdatesEnabled)
    }

    @Test fun sameAppIdentityAsDirect() {
        assertEquals("app.myinventory", BuildConfig.APPLICATION_ID)
        assertEquals(14, BuildConfig.VERSION_CODE)
        assertEquals("12.0.1", BuildConfig.VERSION_NAME)
    }
}
