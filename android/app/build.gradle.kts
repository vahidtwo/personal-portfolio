import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Release signing key lives OUTSIDE the repo. Point MY_INVENTORY_KEYSTORE_PROPERTIES at a
// keystore.properties file (storeFile, storePassword, keyAlias, keyPassword), or keep it at
// ~/.my-inventory-release/keystore.properties. storeFile is resolved relative to that file.
// When neither exists, release builds fall back to the debug key.
val releaseKeystoreProps: File? = (
    System.getenv("MY_INVENTORY_KEYSTORE_PROPERTIES")?.takeIf { it.isNotBlank() }?.let(::File)
        ?: File(System.getProperty("user.home"), ".my-inventory-release/keystore.properties")
    ).takeIf { it.isFile }

android {
    namespace = "app.myinventory"
    compileSdk = 34

    defaultConfig {
        applicationId = "app.myinventory"
        minSdk = 26
        targetSdk = 34
        versionCode = 5
        versionName = "5.0"
    }

    signingConfigs {
        if (releaseKeystoreProps != null) {
            create("release") {
                val props = Properties().apply { releaseKeystoreProps.inputStream().use(::load) }
                storeFile = releaseKeystoreProps.parentFile.resolve(props.getProperty("storeFile"))
                storePassword = props.getProperty("storePassword")
                keyAlias = props.getProperty("keyAlias")
                keyPassword = props.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            isDebuggable = false
            signingConfig = if (releaseKeystoreProps != null) {
                signingConfigs.getByName("release")
            } else {
                logger.warn("my-inventory: no release keystore.properties found; signing release with the debug key")
                signingConfigs.getByName("debug")
            }
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
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20231013")
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
