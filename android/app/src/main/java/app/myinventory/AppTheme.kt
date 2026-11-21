package app.myinventory

import android.content.Context
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.content.edit

/** «ظاهر» on this phone only: auto (follow the system), dark or light. Never sent to the server. */
object AppTheme {
    const val KEY = "native_theme"
    const val AUTO = "auto"
    const val DARK = "dark"
    const val LIGHT = "light"

    fun normalize(raw: String?): String = when (raw) { DARK, LIGHT -> raw; else -> AUTO }

    fun nightMode(choice: String): Int = when (normalize(choice)) {
        DARK -> AppCompatDelegate.MODE_NIGHT_YES
        LIGHT -> AppCompatDelegate.MODE_NIGHT_NO
        else -> AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM
    }

    fun current(c: Context): String =
        normalize(c.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE).getString(KEY, AUTO))

    /** At start-up: only a saved dark/light choice changes anything; auto leaves the app as it always was. */
    fun applySaved(c: Context) {
        val choice = current(c)
        if (choice != AUTO) AppCompatDelegate.setDefaultNightMode(nightMode(choice))
    }

    fun set(c: Context, choice: String) {
        val value = normalize(choice)
        c.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE).edit { putString(KEY, value) }
        AppCompatDelegate.setDefaultNightMode(nightMode(value))
    }
}
