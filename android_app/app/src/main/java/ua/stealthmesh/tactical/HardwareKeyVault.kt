package ua.stealthmesh.tactical

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Hardware-backed secret storage using AndroidKeyStore (StrongBox when available, TEE fallback).
 * Ensures tactical group passphrases are never stored in plaintext on the filesystem.
 */
class HardwareKeyVault(private val context: Context) {
    private val keyAlias = "stealth_mesh_master_key_v1"
    private val prefsName = "stealth_mesh_vault"
    private val cipherKey = "enc_group_secret"

    private fun getOrCreateMasterKey(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        ks.getKey(keyAlias, null)?.let { return it as SecretKey }

        val keyGen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        val builder = KeyGenParameterSpec.Builder(
            keyAlias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.PADDING_NONE)
            .setKeySize(256)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            try {
                builder.setIsStrongBoxBacked(true)
                keyGen.init(builder.build())
                return keyGen.generateKey()
            } catch (_: StrongBoxUnavailableException) {
                builder.setIsStrongBoxBacked(false)
            }
        }
        keyGen.init(builder.build())
        return keyGen.generateKey()
    }

    fun storeSecret(secret: String): Boolean {
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateMasterKey())
            val iv = cipher.iv
            val ct = cipher.doFinal(secret.toByteArray(Charsets.UTF_8))
            val blob = Base64.encodeToString(iv + ct, Base64.NO_WRAP)
            context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
                .edit()
                .putString(cipherKey, blob)
                .apply()
            true
        } catch (_: Exception) {
            false
        }
    }

    fun loadSecret(): String? {
        return try {
            val blob = context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
                .getString(cipherKey, null) ?: return null
            val raw = Base64.decode(blob, Base64.NO_WRAP)
            if (raw.size <= 12) return null
            val iv = raw.copyOfRange(0, 12)
            val ct = raw.copyOfRange(12, raw.size)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, getOrCreateMasterKey(), GCMParameterSpec(128, iv))
            String(cipher.doFinal(ct), Charsets.UTF_8)
        } catch (_: Exception) {
            null
        }
    }

    fun wipeAll() {
        try {
            context.getSharedPreferences(prefsName, Context.MODE_PRIVATE)
                .edit()
                .clear()
                .commit()
            val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            if (ks.containsAlias(keyAlias)) {
                ks.deleteEntry(keyAlias)
            }
        } catch (_: Exception) {
        }
    }
}
