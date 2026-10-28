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
        // QA-only overrides (e.g. the throwaway v7 test APK): -PversionCodeOverride=7 -PversionNameOverride=7.0-test
        versionCode = (project.findProperty("versionCodeOverride") as String?)?.toInt() ?: 11
        versionName = (project.findProperty("versionNameOverride") as String?) ?: "11.0"
        // Release: the update check uses the saved server address, https only.
        buildConfigField("String", "UPDATE_BASE_URL", "\"\"")
        buildConfigField("String", "UPDATE_HTTP_HOST", "\"\"")
    }

    buildFeatures {
        buildConfig = true
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
        // QA variant: same applicationId and key as release, but the update check talks to
        // a local test server (tools/qa_update_server.py). Never shipped in app/static.
        create("qa") {
            initWith(getByName("release"))
            matchingFallbacks += listOf("release")
            // -PqaDebuggable lets QA seed on-device prefs with run-as (e.g. an empty v5 SMS phrase).
            isDebuggable = project.hasProperty("qaDebuggable")
            val qaBase = (project.findProperty("qaUpdateBaseUrl") as String?) ?: "http://10.0.2.2:8765"
            buildConfigField("String", "UPDATE_BASE_URL", "\"$qaBase\"")
            buildConfigField("String", "UPDATE_HTTP_HOST", "\"10.0.2.2\"")
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
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation(platform("com.google.firebase:firebase-bom:35.0.2"))
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
        // Brand symbol for setup.html (same files as the web header)
        assetWwwDir.resolve("brand").mkdirs()
        listOf("daraiito-symbol-dark.svg", "daraiito-symbol-light.svg").forEach { n ->
            webStaticDir.resolve("brand/$n").copyTo(assetWwwDir.resolve("brand/$n"), overwrite = true)
        }
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
