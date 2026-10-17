package app.myinventory

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.content.pm.Signature
import android.os.Build
import androidx.core.content.pm.PackageInfoCompat
import java.io.File
import java.security.MessageDigest

/** Checks a downloaded APK before it is ever handed to the installer. */
object ApkVerifier {
    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                digest.update(buffer, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun certDigests(signatures: Array<Signature>?): Set<String> =
        signatures.orEmpty().map { sig ->
            MessageDigest.getInstance("SHA-256").digest(sig.toByteArray()).joinToString("") { "%02x".format(it) }
        }.toSet()

    @Suppress("DEPRECATION")
    private fun signersOf(info: PackageInfo?): Set<String> {
        info ?: return emptySet()
        return if (Build.VERSION.SDK_INT >= 28) {
            val signing = info.signingInfo ?: return emptySet()
            certDigests(signing.apkContentsSigners)
        } else {
            certDigests(info.signatures)
        }
    }

    @Suppress("DEPRECATION")
    private val certFlag: Int
        get() = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

    @Suppress("DEPRECATION")
    fun installedSigners(context: Context): Set<String> =
        signersOf(context.packageManager.getPackageInfo(context.packageName, certFlag))

    /**
     * True only if: the file's SHA-256 equals the server's, it is our package with the
     * announced versionCode, and it is signed by exactly the same certificate as the
     * installed app (and the server's cert_sha256, when given).
     */
    @Suppress("DEPRECATION")
    fun verify(context: Context, file: File, info: UpdateCheck.Info): Boolean = runCatching {
        val expected = info.sha256 ?: return false
        if (!file.isFile || sha256(file) != expected) return false
        val archive = context.packageManager.getPackageArchiveInfo(file.absolutePath, certFlag) ?: return false
        if (archive.packageName != context.packageName) return false
        if (PackageInfoCompat.getLongVersionCode(archive) != info.versionCode) return false
        val apkSigners = signersOf(archive)
        val installed = installedSigners(context)
        if (apkSigners.isEmpty() || apkSigners != installed) return false
        info.certSha256 == null || apkSigners == setOf(info.certSha256)
    }.getOrDefault(false)
}
