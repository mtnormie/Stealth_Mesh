package ua.stealthmesh.tactical

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbConstants
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbDeviceConnection
import android.hardware.usb.UsbEndpoint
import android.hardware.usb.UsbInterface
import android.hardware.usb.UsbManager
import java.nio.charset.StandardCharsets
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Zero-dependency USB Type-C CDC-ACM driver for ESP32-C3 SuperMini (115200 8N1).
 * Operates 100% over wired USB OTG with zero network or Bluetooth permissions.
 */
class UsbCdcDriver(
    private val context: Context,
    private val onLineReceived: (String) -> Unit
) {
    private val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
    private var connection: UsbDeviceConnection? = null
    private var dataInterface: UsbInterface? = null
    private var epIn: UsbEndpoint? = null
    private var epOut: UsbEndpoint? = null
    private val running = AtomicBoolean(false)
    private var readerThread: Thread? = null

    fun isConnected(): Boolean = running.get() && connection != null

    fun connectFirstAvailable(permissionAction: String): Boolean {
        if (isConnected()) return true
        val devices = usbManager.deviceList.values
        if (devices.isEmpty()) return false

        val device: UsbDevice = devices.firstOrNull {
            it.vendorId in setOf(0x303A, 0x1A86, 0x10C4, 0x0403)
        } ?: devices.first()

        if (!usbManager.hasPermission(device)) {
            val pi = PendingIntent.getBroadcast(
                context,
                0,
                Intent(permissionAction),
                PendingIntent.FLAG_IMMUTABLE
            )
            usbManager.requestPermission(device, pi)
            return false
        }
        return openDevice(device)
    }

    private fun openDevice(device: UsbDevice): Boolean {
        val conn = usbManager.openDevice(device) ?: return false
        var foundIn: UsbEndpoint? = null
        var foundOut: UsbEndpoint? = null
        var foundIf: UsbInterface? = null

        for (i in 0 until device.interfaceCount) {
            val usbIf = device.getInterface(i)
            var inEp: UsbEndpoint? = null
            var outEp: UsbEndpoint? = null
            for (j in 0 until usbIf.endpointCount) {
                val ep = usbIf.getEndpoint(j)
                if (ep.type == UsbConstants.USB_ENDPOINT_XFER_BULK) {
                    if (ep.direction == UsbConstants.USB_DIR_IN) inEp = ep
                    else if (ep.direction == UsbConstants.USB_DIR_OUT) outEp = ep
                }
            }
            if (inEp != null && outEp != null) {
                foundIf = usbIf
                foundIn = inEp
                foundOut = outEp
                break
            }
        }

        if (foundIf == null || foundIn == null || foundOut == null) {
            conn.close()
            return false
        }

        conn.claimInterface(foundIf, true)
        // Configure CDC-ACM line coding: 115200 baud, 1 stop bit, no parity, 8 data bits
        val lineCoding = byteArrayOf(
            0x00, 0xC2.toByte(), 0x01, 0x00, // 115200 LE
            0x00,                            // 1 stop bit
            0x00,                            // no parity
            0x08                             // 8 data bits
        )
        conn.controlTransfer(0x21, 0x20, 0, 0, lineCoding, lineCoding.size, 300)
        // Assert DTR/RTS so ESP32-C3 USB Serial/JTAG streams immediately without resetting into bootloader
        conn.controlTransfer(0x21, 0x22, 0x01, 0, null, 0, 300)

        connection = conn
        dataInterface = foundIf
        epIn = foundIn
        epOut = foundOut
        running.set(true)

        readerThread = Thread({ readLoop() }, "StealthMesh-UsbReader").apply {
            isDaemon = true
            start()
        }
        return true
    }

    private fun readLoop() {
        val buf = ByteArray(512)
        val sb = StringBuilder()
        while (running.get()) {
            val conn = connection ?: break
            val inEndpoint = epIn ?: break
            val n = conn.bulkTransfer(inEndpoint, buf, buf.size, 250)
            if (n > 0) {
                val chunk = String(buf, 0, n, StandardCharsets.UTF_8)
                sb.append(chunk)
                while (true) {
                    val idx = sb.indexOf("\n")
                    if (idx < 0) break
                    val line = sb.substring(0, idx).trim()
                    sb.delete(0, idx + 1)
                    if (line.isNotEmpty()) {
                        onLineReceived(line)
                    }
                }
            }
        }
    }

    @Synchronized
    fun writeLine(line: String): Boolean {
        val conn = connection ?: return false
        val outEndpoint = epOut ?: return false
        val payload = (if (line.endsWith("\n")) line else "$line\n").toByteArray(StandardCharsets.UTF_8)
        val written = conn.bulkTransfer(outEndpoint, payload, payload.size, 500)
        return written >= 0
    }

    @Synchronized
    fun close() {
        running.set(false)
        try {
            dataInterface?.let { connection?.releaseInterface(it) }
            connection?.close()
        } catch (_: Exception) {
        } finally {
            connection = null
            dataInterface = null
            epIn = null
            epOut = null
        }
    }
}
