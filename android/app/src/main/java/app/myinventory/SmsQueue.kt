package app.myinventory

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * SMS spends that arrived while signed out. Kept in app-private storage, encrypted with an
 * AndroidKeyStore AES-GCM key. Each entry is bound to the username that was signed in last; after a login
 * only that user's entries are sent, others stay queued for their owner. Entries expire after [MAX_AGE_DAYS].
 * Logout does not clear the queue (spends that arrive after logout are the point).
 * Only amount, masked note, idempotency key, time and username are stored (the raw SMS stays in SmsLog).
 */
object SmsQueue {
    data class Entry(val amountToman: String, val note: String, val idem: String, val at: Long, val user: String)

    enum class Result { DONE, KEEP_AND_STOP, KEEP, DROP }

    const val MAX_ENTRIES = 500
    const val MAX_AGE_DAYS = 7
    private const val DAY_MS = 24L * 60 * 60 * 1000
    private const val TAG = "SmsQueue"
    private const val FILE = "sms-queue.bin"
    private const val KEY_ALIAS = "sms-queue-key"
    private val lock = Any()

    // ---- pure logic (unit-tested) ----

    fun encode(entries: List<Entry>): String = JSONArray().apply {
        entries.forEach { put(JSONObject().put("a", it.amountToman).put("n", it.note).put("k", it.idem).put("t", it.at).put("u", it.user)) }
    }.toString()

    fun decode(text: String): List<Entry> = runCatching {
        val arr = JSONArray(text)
        (0 until arr.length()).map { arr.getJSONObject(it) }
            .map { Entry(it.getString("a"), it.optString("n"), it.getString("k"), it.getLong("t"), it.optString("u")) }
    }.getOrDefault(emptyList())

    /** Adds an entry unless its key is already queued; oldest entries fall off past [MAX_ENTRIES]. */
    fun added(entries: List<Entry>, e: Entry): List<Entry> =
        if (entries.any { it.idem == e.idem }) entries else (entries + e).takeLast(MAX_ENTRIES)

    fun normalizeUser(name: String?): String = name.orEmpty().trim().lowercase()

    fun expired(e: Entry, now: Long): Boolean = now - e.at > MAX_AGE_DAYS * DAY_MS

    /** Entries to send for [user] now, and the ones to keep (other users, not yet expired). Expired ones are dropped. */
    fun split(entries: List<Entry>, user: String, now: Long): Pair<List<Entry>, List<Entry>> {
        val live = entries.filterNot { expired(it, now) }
        val u = normalizeUser(user)
        val mine = if (u.isEmpty()) emptyList() else live.filter { normalizeUser(it.user) == u }
        return mine to live.filterNot { it in mine }
    }

    /** 2xx saved (or duplicate), 401/403 still signed out, 4xx bad entry, else retry later. */
    fun classify(code: Int?): Result = when {
        code == null -> Result.KEEP
        code in 200..299 -> Result.DONE
        code == 401 || code == 403 -> Result.KEEP_AND_STOP
        code in 300..399 -> Result.KEEP_AND_STOP
        code in 400..499 -> Result.DROP
        else -> Result.KEEP
    }

    fun payload(e: Entry): JSONObject = JSONObject()
        .put("amount_toman", e.amountToman).put("note", e.note)
        .put("idempotency_key", e.idem).put("sms_at", e.at)

    // ---- storage ----

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return gen.generateKey()
    }

    private fun file(context: Context) = File(context.filesDir, FILE)

    fun load(context: Context): List<Entry> = synchronized(lock) {
        val f = file(context)
        if (!f.exists()) return emptyList()
        runCatching {
            val bytes = f.readBytes()
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, bytes.copyOfRange(0, 12)))
            decode(String(c.doFinal(bytes.copyOfRange(12, bytes.size)), Charsets.UTF_8))
        }.onFailure { Log.w(TAG, "load failed", it) }.getOrDefault(emptyList())
    }

    private fun save(context: Context, entries: List<Entry>) {
        val f = file(context)
        if (entries.isEmpty()) { f.delete(); return }
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, key())
        val out = c.iv + c.doFinal(encode(entries).toByteArray(Charsets.UTF_8))
        val tmp = File(f.parentFile, "$FILE.tmp")
        tmp.writeBytes(out)
        if (!tmp.renameTo(f)) { f.delete(); tmp.renameTo(f) }
    }

    fun add(context: Context, e: Entry) = synchronized(lock) { save(context, added(load(context), e)) }

    fun size(context: Context): Int = load(context).size

    fun post(base: String, cookie: String, body: JSONObject): Int {
        val connection = (URL("$base/api/sms-spend").openConnection() as HttpURLConnection)
        connection.requestMethod = "POST"
        connection.instanceFollowRedirects = false
        connection.doOutput = true
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Cookie", cookie)
        connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        connection.disconnect()
        return code
    }

    /**
     * Sends queued entries with the signed-in session; call off the main thread.
     * Returns how many were saved. Same idempotency key as the live path, so the server dedupes.
     */
    fun flush(context: Context, base: String, cookie: String, user: String, now: Long = System.currentTimeMillis()): Int = synchronized(lock) {
        val all = load(context)
        if (all.isEmpty()) return 0
        val (left, others) = split(all, user, now)
        var saved = 0
        val keep = others.toMutableList()
        for ((i, e) in left.withIndex()) {
            val code = runCatching { post(base, cookie, payload(e)) }.getOrNull()
            when (classify(code)) {
                Result.DONE -> saved++
                Result.DROP -> Unit
                Result.KEEP -> keep += e
                Result.KEEP_AND_STOP -> { keep += left.subList(i, left.size); break }
            }
        }
        runCatching { save(context, keep) }.onFailure { Log.w(TAG, "save failed", it) }
        saved
    }
}
