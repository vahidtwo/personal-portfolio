package app.myinventory

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.net.ServerSocket

class OfflineFallbackTest {
    private lateinit var server: ServerSocket
    @Volatile private var code = 200
    @Volatile private var body = "{\"ok\":true}"
    @Volatile private var delayMs = 0L
    @Volatile private var location: String? = null
    private val base get() = "http://127.0.0.1:${server.localPort}"

    @Before fun start() {
        server = ServerSocket(0, 50, java.net.InetAddress.getByName("127.0.0.1"))
        Thread {
            while (!server.isClosed) {
                val sock = try { server.accept() } catch (e: Exception) { break }
                Thread {
                    sock.use { s ->
                        try {
                            val r = s.getInputStream().bufferedReader()
                            while (true) { val l = r.readLine() ?: break; if (l.isEmpty()) break }
                            if (delayMs > 0) Thread.sleep(delayMs)
                            val bytes = body.toByteArray()
                            val sb = StringBuilder("HTTP/1.1 $code X\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n")
                            location?.let { sb.append("Location: $it\r\n") }
                            sb.append("\r\n")
                            val o = s.getOutputStream(); o.write(sb.toString().toByteArray()); o.write(bytes); o.flush()
                        } catch (e: Exception) {}
                    }
                }.apply { isDaemon = true }.start()
            }
        }.apply { isDaemon = true }.start()
    }

    @After fun stop() = server.close()

    @Test fun probeOk() = assertTrue(HealthProbe.isUp(base))

    @Test fun probeWrongBodyOrStatus() {
        body = "<html>بدون اتصال</html>"; assertFalse(HealthProbe.isUp(base))
        body = "{\"ok\":false}"; assertFalse(HealthProbe.isUp(base))
        body = "{\"ok\":true}"; code = 503; assertFalse(HealthProbe.isUp(base))
    }

    @Test fun probeDoesNotFollowRedirects() {
        code = 302; location = "/elsewhere"; body = "{\"ok\":true}"
        assertFalse(HealthProbe.isUp(base))
    }

    @Test fun probeTimesOutQuickly() {
        delayMs = 3000
        val t0 = System.nanoTime()
        assertFalse(HealthProbe.isUp(base, timeoutMs = 500))
        assertTrue((System.nanoTime() - t0) / 1_000_000 < 2500)
        assertEquals(3500, HealthProbe.TIMEOUT_MS)
    }

    @Test fun probeConnectionRefused() {
        val port = ServerSocket(0).use { it.localPort }
        assertFalse(HealthProbe.isUp("http://127.0.0.1:$port"))
    }

    @Test fun offlineMarkerDetection() {
        assertTrue(ServerAddress.isOfflinePage("\"1\""))
        assertFalse(ServerAddress.isOfflinePage("\"0\""))
        assertFalse(ServerAddress.isOfflinePage("null"))
        assertFalse(ServerAddress.isOfflinePage(null))
        assertFalse(ServerAddress.isOfflinePage("1x"))
        assertTrue(ServerAddress.OFFLINE_MARKER_JS.contains("meta[name=\"x-offline\"]"))
    }

    @Test fun launchProbeOnlyWhenMovedAndUnconfirmed() {
        val new = ServerAddress.DEFAULT
        assertTrue(ServerAddress.shouldProbeOnLaunch(new, migrated = true, confirmed = false, probedThisLaunch = false))
        assertFalse(ServerAddress.shouldProbeOnLaunch(new, true, false, probedThisLaunch = true))
        assertFalse(ServerAddress.shouldProbeOnLaunch(new, true, confirmed = true, probedThisLaunch = false))
        assertFalse(ServerAddress.shouldProbeOnLaunch(new, migrated = false, confirmed = false, probedThisLaunch = false)) // fresh install
        assertFalse(ServerAddress.shouldProbeOnLaunch(ServerAddress.OLD_DEFAULT, true, false, false))
        assertFalse(ServerAddress.shouldProbeOnLaunch("https://my.server.example", true, false, false))
    }

    @Test fun probeFailureUsesSameFallbackLimits() {
        val new = ServerAddress.DEFAULT
        // the native probe passes "$new/health" as the failed URL
        assertTrue(ServerAddress.shouldFallBack(new, true, false, "$new/health"))
        assertFalse(ServerAddress.shouldFallBack(new, true, fallbackThisLaunch = true, failedUrl = "$new/health"))
        // offline page on the new host -> same path
        assertTrue(ServerAddress.shouldFallBack(new, true, false, "$new/dashboard"))
    }
}
