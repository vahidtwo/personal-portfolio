plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.myinventory"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.myinventory"
        minSdk = 26
        targetSdk = 34
        versionCode = 3
        versionName = "3.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging")
}

val webStaticDir = file("../../app/static")
val assetWwwDir = file("src/main/assets/www/static")

tasks.register("syncWebAssets") {
    inputs.dir(webStaticDir)
    outputs.dir(assetWwwDir)
    doLast {
        val style = webStaticDir.resolve("style.css")
        val theme = webStaticDir.resolve("theme.js")
        val logo = webStaticDir.resolve("logo.svg")
        require(style.isFile) { "Missing ${style.path} — run from repo with app/static" }
        assetWwwDir.mkdirs()
        assetWwwDir.resolve("fonts").mkdirs()
        style.copyTo(assetWwwDir.resolve("style.css"), overwrite = true)
        theme.copyTo(assetWwwDir.resolve("theme.js"), overwrite = true)
        logo.copyTo(assetWwwDir.resolve("logo.svg"), overwrite = true)
        val fonts = webStaticDir.resolve("fonts")
        if (fonts.isDirectory) {
            fonts.listFiles()?.filter { it.isFile }?.forEach { font ->
                font.copyTo(assetWwwDir.resolve("fonts/${font.name}"), overwrite = true)
            }
        }
        val css = assetWwwDir.resolve("style.css").readText()
        assetWwwDir.resolve("style.css").writeText(
            css.replace("url(\"/static/", "url(\"").replace("url('/static/", "url('"),
        )
    }
}

tasks.named("preBuild").configure {
    dependsOn("syncWebAssets")
}

apply(plugin = "com.google.gms.google-services")
