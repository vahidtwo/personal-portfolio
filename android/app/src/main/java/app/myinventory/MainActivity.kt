package app.myinventory

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.ScrollView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.edit

class MainActivity : AppCompatActivity() {
    private lateinit var web: WebView
    private lateinit var setupPanel: View
    private lateinit var trustPanel: ScrollView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        web = findViewById(R.id.web)
        setupPanel = findViewById(R.id.setupPanel)
        trustPanel = findViewById(R.id.trustPanel)
        val urlField = findViewById<EditText>(R.id.siteUrl)
        val phraseField = findViewById<EditText>(R.id.smsPhrase)
        urlField.setText(prefs.getString(KEY_URL, "") ?: "")
        phraseField.setText(prefs.getString(KEY_PHRASE, DEFAULT_PHRASE) ?: DEFAULT_PHRASE)

        CookieManager.getInstance().setAcceptCookie(true)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = false
        web.settings.allowContentAccess = false
        web.settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            web.settings.safeBrowsingEnabled = true
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val base = (prefs.getString(KEY_URL, "") ?: "").trimEnd('/')
                val host = runCatching { Uri.parse(base).host }.getOrNull()
                val reqHost = request.url.host
                if (host != null && reqHost != null && host == reqHost) return false
                return true
            }
        }

        findViewById<Button>(R.id.trustContinue).setOnClickListener {
            prefs.edit { putBoolean(KEY_TRUST, true) }
            trustPanel.visibility = View.GONE
            refreshPanels(prefs)
        }

        findViewById<Button>(R.id.saveSite).setOnClickListener {
            val url = urlField.text.toString().trim().trimEnd('/')
            val phrase = phraseField.text.toString().trim().ifEmpty { DEFAULT_PHRASE }
            prefs.edit {
                putString(KEY_URL, url)
                putString(KEY_PHRASE, phrase)
            }
            askSmsPermission()
            if (url.startsWith("https://")) {
                web.loadUrl(url)
                setupPanel.visibility = View.GONE
            }
        }

        findViewById<Button>(R.id.openWeb).setOnClickListener {
            setupPanel.visibility = View.GONE
        }

        if (!prefs.getBoolean(KEY_TRUST, false)) {
            trustPanel.visibility = View.VISIBLE
        }
        refreshPanels(prefs)
        askSmsPermission()
    }

    private fun refreshPanels(prefs: android.content.SharedPreferences) {
        if (!prefs.getBoolean(KEY_TRUST, false)) return
        val saved = prefs.getString(KEY_URL, "") ?: ""
        if (saved.startsWith("https://")) {
            web.loadUrl(saved)
            setupPanel.visibility = View.GONE
        } else {
            setupPanel.visibility = View.VISIBLE
        }
    }

    private fun askSmsPermission() {
        val needed = mutableListOf(Manifest.permission.RECEIVE_SMS)
        if (Build.VERSION.SDK_INT >= 33) {
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = needed.filter {
            ActivityCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 1)
        }
    }

    companion object {
        const val PREFS = "app.myinventory"
        const val KEY_URL = "base_url"
        const val KEY_PHRASE = "sms_phrase"
        const val KEY_TRUST = "trust_ok"
        const val DEFAULT_PHRASE = "برداشت"
    }
}
