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
        assertEquals(22, BuildConfig.VERSION_CODE)
        assertEquals("12.1.6", BuildConfig.VERSION_NAME)
    }
}
