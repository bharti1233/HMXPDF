package com.hmx.pdf.backend

import android.content.Context
import android.content.pm.PackageInfo
import android.os.Build
import com.hmx.pdf.BuildConfig

/** Staging-only backend configuration. Debug and release builds compile a disabled client. */
object BackendConfig {
    val enabled: Boolean get() = BuildConfig.HMX_BACKEND_ENABLED
    val functionsBaseUrl: String get() = BuildConfig.HMX_BACKEND_URL.trimEnd('/')
    val publishableKey: String get() = BuildConfig.HMX_BACKEND_PUBLISHABLE_KEY
}

object AppInfo {
    fun versionName(context: Context): String = try {
        @Suppress("DEPRECATION")
        context.packageManager.getPackageInfo(context.packageName, 0).versionName ?: "unknown"
    } catch (e: Exception) {
        "unknown"
    }

    fun versionCode(context: Context): Int = try {
        val info: PackageInfo = context.packageManager.getPackageInfo(context.packageName, 0)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) info.longVersionCode.toInt() else info.versionCode
    } catch (e: Exception) {
        0
    }
}
