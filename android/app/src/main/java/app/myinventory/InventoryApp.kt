package app.myinventory

import android.app.Application

class InventoryApp : Application() {
    override fun onCreate() {
        super.onCreate()
        PushRegistrar.initFromCache(this)
    }
}
