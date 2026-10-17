package app.myinventory

import android.content.Context
import android.os.Handler
import android.os.Looper
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * Downloads the APK into app-private cache (resumable with HTTP Range), then verifies it.
 * Chosen over DownloadManager: DownloadManager can't write to app-private internal storage,
 * pauses silently ("waiting for network") instead of failing, and is hard to cancel/verify.
 */
class UpdateDownloader(
    context: Context,
    private val info: UpdateCheck.Info,
    private val url: String,
    private val listener: Listener,
) {
    interface Listener {
        fun onProgress(done: Long, total: Long)
        fun onReady(file: File)
        fun onFailed()
    }

    private val appContext = context.applicationContext
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var cancelled = false

    val apkFile: File get() = File(dir(appContext), "my-inventory-${info.versionCode}.apk")
    private val partFile: File get() = File(dir(appContext), "my-inventory-${info.versionCode}.apk.part")

    fun start() {
        cancelled = false
        thread(name = "update-download", isDaemon = true) {
            try {
                cleanupOtherVersions()
                val apk = apkFile
                if (apk.isFile) {
                    if (ApkVerifier.verify(appContext, apk, info)) {
                        post { listener.onReady(apk) }
                        return@thread
                    }
                    apk.delete()
                }
                download()
                if (cancelled) return@thread
                if (!partFile.renameTo(apk)) throw java.io.IOException("rename failed")
                if (ApkVerifier.verify(appContext, apk, info)) {
                    post { listener.onReady(apk) }
                } else {
                    // Wrong checksum or signature: never keep or install it.
                    apk.delete()
                    partFile.delete()
                    post { listener.onFailed() }
                }
            } catch (_: Throwable) {
                if (!cancelled) post { listener.onFailed() } // partial file kept for resume
            }
        }
    }

    /** «لغو»: stop and delete the partial file. */
    fun cancel() {
        cancelled = true
        thread(isDaemon = true) {
            Thread.sleep(300)
            partFile.delete()
        }
    }

    private fun download() {
        val part = partFile
        var offset = if (part.isFile) part.length() else 0L
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 10_000
            conn.readTimeout = 15_000
            conn.instanceFollowRedirects = false
            conn.useCaches = false
            if (offset > 0) conn.setRequestProperty("Range", "bytes=$offset-")
            val code = conn.responseCode
            val append = when (code) {
                206 -> true
                200 -> { offset = 0; false }
                416 -> { part.delete(); throw java.io.IOException("range not satisfiable") }
                else -> throw java.io.IOException("HTTP $code")
            }
            val length = conn.getHeaderField("Content-Length")?.toLongOrNull() ?: -1L
            val total = if (length > 0) offset + length else (info.sizeBytes ?: -1L)
            var done = offset
            var lastPost = 0L
            conn.inputStream.use { input ->
                FileOutputStream(part, append).use { out ->
                    val buffer = ByteArray(32 * 1024)
                    while (!cancelled) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        out.write(buffer, 0, n)
                        done += n
                        val now = System.currentTimeMillis()
                        if (now - lastPost > 150) {
                            lastPost = now
                            val d = done
                            post { listener.onProgress(d, total) }
                        }
                    }
                }
            }
            if (cancelled) return
            if (total > 0 && done != total) throw java.io.IOException("incomplete")
            val d = done
            post { listener.onProgress(d, if (total > 0) total else d) }
        } finally {
            conn.disconnect()
        }
    }

    private fun cleanupOtherVersions() {
        val keep = setOf(apkFile.name, partFile.name)
        dir(appContext).listFiles()?.filter { it.name !in keep }?.forEach { it.delete() }
    }

    private fun post(block: () -> Unit) {
        if (!cancelled) main.post { if (!cancelled) block() }
    }

    companion object {
        fun dir(context: Context): File = File(context.cacheDir, "updates").apply { mkdirs() }
    }
}
