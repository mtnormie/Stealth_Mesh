plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ua.stealthmesh.tactical"
    compileSdk = 34

    defaultConfig {
        applicationId = "ua.stealthmesh.tactical"
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "1.0.0-emcon"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
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
    // Zero external network libraries — 100% Android SDK native UsbManager + WebView
}
