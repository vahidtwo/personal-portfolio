package app.myinventory

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PushOptionsTest {
    private val android = """{"appId":"1:123456789012:android:abcdef0123456789","apiKey":"AIzaFakeFakeFakeFakeFakeFakeFakeFake000","projectId":"fake-project","senderId":"123456789012"}"""

    @Test fun readsTheAndroidPartOfServerConfig() {
        val o = PushOptions.fromJson("""{"enabled":true,"config":{},"android":$android}""")!!
        assertEquals("1:123456789012:android:abcdef0123456789", o.appId)
        assertEquals("fake-project", o.projectId)
        assertEquals("123456789012", o.senderId)
        assertEquals(o, PushOptions.fromJson(o.toJson()))
    }

    @Test fun rejectsMissingOrMismatchedValues() {
        assertNull(PushOptions.fromJson(null))
        assertNull(PushOptions.fromJson(""))
        assertNull(PushOptions.fromJson("not json"))
        assertNull(PushOptions.fromJson("""{"enabled":true,"android":null}"""))
        assertNull(PushOptions.fromJson(android.replace("android:abcdef", "web:abcdef")))
        assertNull(PushOptions.fromJson(android.replace("\"senderId\":\"123456789012\"", "\"senderId\":\"999\"")))
        assertNull(PushOptions.fromJson(android.replace("fake-project", "")))
        assertNull(PushOptions.fromJson(android.replace("AIzaFakeFakeFakeFakeFakeFakeFakeFake000", "REPLACE ME")))
    }

    @Test fun registersOnChangeForceOrAfterTheInterval() {
        val now = 10L * PushState.REREGISTER_MS
        assertTrue(PushState.shouldRegister(force = false, token = "t", lastToken = null, lastAt = 0L, now = now))
        assertTrue(PushState.shouldRegister(force = false, token = "t2", lastToken = "t", lastAt = now, now = now))
        assertTrue(PushState.shouldRegister(force = true, token = "t", lastToken = "t", lastAt = now, now = now))
        assertFalse(PushState.shouldRegister(force = false, token = "t", lastToken = "t", lastAt = now - 1000, now = now))
        assertTrue(PushState.shouldRegister(force = false, token = "t", lastToken = "t", lastAt = now - PushState.REREGISTER_MS, now = now))
        assertTrue(PushState.shouldRegister(force = false, token = "t", lastToken = "t", lastAt = now + 5000, now = now))
    }

    @Test fun httpCodesMapToStates() {
        assertEquals(PushState.OK, PushState.stateForHttp(200))
        assertEquals(PushState.LOGIN, PushState.stateForHttp(401))
        assertEquals(PushState.REGISTER_FAILED, PushState.stateForHttp(403))
        assertEquals(PushState.REGISTER_FAILED, PushState.stateForHttp(-1))
    }
}
