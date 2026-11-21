package app.myinventory

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.CookieManager
import androidx.core.content.edit
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

object PushRegistrar {
    private const val TAG = "InventoryPush"
    private const val KEY_OPTIONS = "push_android_options"
    private const val KEY_STATE = "push_state"
    private const val KEY_DETAIL = "push_detail"
    private const val KEY_TOKEN = "push_registered_token"
    private const val KEY_AT = "push_registered_at"

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)

    private fun base(context: Context): String =
        (prefs(context).getString(MainActivity.KEY_URL, "") ?: "").trimEnd('/')

    fun state(context: Context): String = prefs(context).getString(KEY_STATE, PushState.IDLE) ?: PushState.IDLE
    fun detail(context: Context): String = prefs(context).getString(KEY_DETAIL, "") ?: ""

    private fun setState(context: Context, state: String, detail: String = "") {
        prefs(context).edit { putString(KEY_STATE, state); putString(KEY_DETAIL, detail.take(80)) }
    }

    /** Start Firebase from the options cached on an earlier run (app start, before any FCM callback). */
    fun initFromCache(context: Context): Boolean {
        if (FirebaseApp.getApps(context).isNotEmpty()) return true
        val options = PushOptions.fromJson(prefs(context).getString(KEY_OPTIONS, null)) ?: return false
        return initialize(context, options)
    }

    private fun initialize(context: Context, options: PushOptions): Boolean = runCatching {
        if (FirebaseApp.getApps(context).isEmpty()) {
            FirebaseApp.initializeApp(
                context.applicationContext,
                FirebaseOptions.Builder()
                    .setApplicationId(options.appId)
                    .setApiKey(options.apiKey)
                    .setProjectId(options.projectId)
                    .setGcmSenderId(options.senderId)
                    .build(),
            )
        }
        true
    }.getOrElse { Log.w(TAG, "Firebase init failed: ${it.javaClass.simpleName}"); false }

    /** Get this install's FCM token and send it to the server. [force]: the settings button asked. */
    fun registerFcmToken(context: Context, force: Boolean = false) {
        val app = context.applicationContext
        val base = base(app)
        if (!base.startsWith("https://")) return
        if (force) setState(app, PushState.PENDING)
        thread {
            val fetched = fetchOptions(base)
            if (fetched != null) prefs(app).edit { putString(KEY_OPTIONS, fetched.toJson()) }
            Handler(Looper.getMainLooper()).post {
                if (!initFromCache(app)) {
                    setState(app, PushState.UNCONFIGURED)
                    return@post
                }
                requestToken(app, base, force)
            }
        }
    }

    private fun requestToken(context: Context, base: String, force: Boolean) {
        runCatching {
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                val token = if (task.isSuccessful) task.result else null
                if (token.isNullOrBlank()) {
                    val reason = task.exception?.message ?: task.exception?.javaClass?.simpleName ?: ""
                    Log.w(TAG, "FCM token failed: $reason")
                    setState(context, PushState.TOKEN_FAILED, reason)
                    return@addOnCompleteListener
                }
                registerToken(context, base, token, force)
            }
        }.onFailure {
            Log.w(TAG, "FCM unavailable: ${it.javaClass.simpleName}")
            setState(context, PushState.TOKEN_FAILED, it.javaClass.simpleName)
        }
    }

    fun registerToken(context: Context, base: String, token: String, force: Boolean = true) {
        val app = context.applicationContext
        if (!base.startsWith("https://")) return
        val p = prefs(app)
        val now = System.currentTimeMillis()
        if (!PushState.shouldRegister(force, token, p.getString(KEY_TOKEN, null), p.getLong(KEY_AT, 0L), now)) {
            setState(app, PushState.OK)
            return
        }
        thread {
            val cookie = readCookie(base)
            if (cookie.isNullOrBlank()) {
                setState(app, PushState.LOGIN)
                return@thread
            }
            val code = runCatching { postRegister(base, cookie, token) }.getOrDefault(-1)
            val state = PushState.stateForHttp(code)
            if (state == PushState.OK) p.edit { putString(KEY_TOKEN, token); putLong(KEY_AT, now) }
            setState(app, state, if (state == PushState.OK) "" else "HTTP $code")
        }
    }

    private fun fetchOptions(base: String): PushOptions? = runCatching {
        val connection = URL("$base/api/push/config").openConnection() as HttpURLConnection
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        try {
            if (connection.responseCode !in 200..299) return@runCatching null
            val body = connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            PushOptions.fromJson(body)
        } finally {
            connection.disconnect()
        }
    }.getOrNull()

    private fun readCookie(base: String): String? {
        val latch = CountDownLatch(1)
        var cookie: String? = null
        Handler(Looper.getMainLooper()).post {
            cookie = CookieManager.getInstance().getCookie(base)
            latch.countDown()
        }
        latch.await(5, TimeUnit.SECONDS)
        return cookie
    }

    private fun postRegister(base: String, cookie: String, token: String): Int {
        val connection = (URL("$base/api/push/register").openConnection() as HttpURLConnection)
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.connectTimeout = 15000
        connection.readTimeout = 15000
        connection.setRequestProperty("Content-Type", "application/json")
        connection.setRequestProperty("Cookie", cookie)
        val payload = JSONObject()
        payload.put("token", token)
        payload.put("platform", "android")
        try {
            connection.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            return connection.responseCode
        } finally {
            connection.disconnect()
        }
    }
}
