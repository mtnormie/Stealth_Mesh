package ua.stealthmesh.tactical

import android.annotation.SuppressLint
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import org.json.JSONObject

/**
 * Tactical Messenger Activity for Android (100% Offline, USB-C OTG only, 0.00 mW Wi-Fi/BT).
 * Auto-launches when the ESP32-C3 USB Type-C cable is plugged into the fighter's smartphone.
 */
class MainActivity : Activity() {

    companion object {
        private const val ACTION_USB_PERMISSION = "ua.stealthmesh.tactical.USB_PERMISSION"
    }

    private lateinit var webView: WebView
    private lateinit var usbDriver: UsbCdcDriver
    private lateinit var keyVault: HardwareKeyVault

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                ACTION_USB_PERMISSION, UsbManager.ACTION_USB_DEVICE_ATTACHED -> {
                    usbDriver.connectFirstAvailable(ACTION_USB_PERMISSION)
                }
                UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                    usbDriver.close()
                }
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        webView = WebView(this)
        setContentView(webView)
        keyVault = HardwareKeyVault(this)

        usbDriver = UsbCdcDriver(this) { rawLine ->
            runOnUiThread {
                val escaped = JSONObject.quote(rawLine)
                webView.evaluateJavascript("window.onNativeUsbLine && window.onNativeUsbLine($escaped);", null)
            }
        }

        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.blockNetworkLoads = true // Enforce 100% offline zero-network operation

        webView.addJavascriptInterface(AndroidUsbJsBridge(), "AndroidUsbBridge")
        webView.loadUrl("file:///android_asset/index.html")

        val filter = IntentFilter().apply {
            addAction(ACTION_USB_PERMISSION)
            addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED)
            addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(usbReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(usbReceiver, filter)
        }

        usbDriver.connectFirstAvailable(ACTION_USB_PERMISSION)
    }

    override fun onDestroy() {
        try {
            unregisterReceiver(usbReceiver)
        } catch (_: Exception) {
        }
        usbDriver.close()
        super.onDestroy()
    }

    inner class AndroidUsbJsBridge {
        @JavascriptInterface
        fun connectUsb(): Boolean {
            return usbDriver.connectFirstAvailable(ACTION_USB_PERMISSION)
        }

        @JavascriptInterface
        fun isConnected(): Boolean {
            return usbDriver.isConnected()
        }

        @JavascriptInterface
        fun sendLine(line: String): Boolean {
            return usbDriver.writeLine(line)
        }

        @JavascriptInterface
        fun storeSecret(secret: String): Boolean {
            return keyVault.storeSecret(secret)
        }

        @JavascriptInterface
        fun loadSecret(): String {
            return keyVault.loadSecret() ?: ""
        }

        @JavascriptInterface
        fun wipeSecrets(): Boolean {
            usbDriver.writeLine("WIPE")
            keyVault.wipeAll()
            return true
        }
    }
}
