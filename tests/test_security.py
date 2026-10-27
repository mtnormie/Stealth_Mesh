"""Tests for AES-256-GCM encryption, HKDF, HMAC, replay protection, and group messaging."""

import unittest

from app.main import _require_float, _require_str
from app.services.group_service import GroupService
from security.authentication import MessageAuthenticator, SignedEnvelope
from security.encryption import EncryptedPayload, decrypt, encrypt
from security.integrity import ReplayWindow, compute_hmac, verify_hmac
from security.key_manager import (
    KeyManager,
    derive_subkey,
    generate_group_key,
    generate_invitation_token,
    hkdf_sha256,
)


class EncryptionTests(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip_and_unique_nonce(self) -> None:
        key = generate_group_key()
        self.assertEqual(len(key), 32)
        aad = b'{"group":"g1","sender":"alice"}'
        first = encrypt(key, b"secret message", aad)
        second = encrypt(key, b"secret message", aad)
        self.assertNotEqual(first.nonce, second.nonce)
        self.assertEqual(decrypt(key, first, aad), b"secret message")
        restored = EncryptedPayload.from_dict(first.to_dict())
        self.assertEqual(decrypt(key, restored, aad), b"secret message")

    def test_tampering_and_wrong_key_are_rejected(self) -> None:
        key = generate_group_key()
        other_key = generate_group_key()
        payload = encrypt(key, b"payload", b"aad-1")
        with self.assertRaises(ValueError):
            decrypt(other_key, payload, b"aad-1")
        with self.assertRaises(ValueError):
            decrypt(key, payload, b"aad-2")
        tampered = EncryptedPayload(
            payload.nonce,
            bytes([payload.ciphertext[0] ^ 0x01]) + payload.ciphertext[1:],
        )
        with self.assertRaises(ValueError):
            decrypt(key, tampered, b"aad-1")

    def test_invalid_inputs_and_malformed_dict_are_rejected(self) -> None:
        key = generate_group_key()
        with self.assertRaises(ValueError):
            encrypt(b"short", b"msg")
        with self.assertRaises(TypeError):
            encrypt(key, "not-bytes")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            EncryptedPayload(b"short", b"0" * 16)
        with self.assertRaises(ValueError):
            EncryptedPayload.from_dict({"nonce": "bad!", "ciphertext": "bad!"})
        with self.assertRaises(ValueError):
            EncryptedPayload.from_dict({})

    def test_nist_sp800_38d_known_answer_vector(self) -> None:
        key = bytes.fromhex("00" * 32)
        nonce = bytes.fromhex("00" * 12)
        tag = bytes.fromhex("530f8afbc74536b9a963b4f1c4cb738b")
        payload = EncryptedPayload(nonce=nonce, ciphertext=tag)
        self.assertEqual(decrypt(key, payload, b""), b"")

    def test_rfc5869_hkdf_sha256_test_vector_and_key_manager(self) -> None:
        # RFC 5869 Test Case 1
        ikm = bytes.fromhex("0b" * 22)
        salt = bytes.fromhex("000102030405060708090a0b0c")
        info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
        expected_okm = bytes.fromhex(
            "3cb25f25faacd57a90434f64d0362f2a"
            "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
            "34007208d5b887185865"
        )
        self.assertEqual(hkdf_sha256(ikm, salt=salt, info=info, length=42), expected_okm)

        master = generate_group_key()
        sub_enc = derive_subkey(master, "enc", context=b"g1")
        sub_mac = derive_subkey(master, "mac", context=b"g1")
        self.assertNotEqual(sub_enc, sub_mac)

        km = KeyManager(max_retained_versions=2)
        v1 = km.register_group("g1")
        self.assertEqual(v1.version, 1)
        v2 = km.rotate_group_key("g1")
        v3 = km.rotate_group_key("g1")
        self.assertEqual(v3.version, 3)
        self.assertEqual(km.get_key("g1", 2), v2.key)
        with self.assertRaises(KeyError):
            km.get_key("g1", 1)  # evicted by max_retained_versions=2
        km.revoke_group("g1")
        with self.assertRaises(KeyError):
            km.active_key("g1")

    def test_hmac_sender_authentication_and_replay_protection(self) -> None:
        key = generate_group_key()
        tag = compute_hmac(key, b"frame-bytes")
        self.assertTrue(verify_hmac(key, b"frame-bytes", tag))
        self.assertFalse(verify_hmac(key, b"tampered", tag))

        window = ReplayWindow(window_size=4)
        auth = MessageAuthenticator(replay_window=window)

        env1 = auth.seal(key, group_id="g1", sender="N1", sequence=1, plaintext=b"msg-1")
        env2 = auth.seal(key, group_id="g1", sender="N1", sequence=2, plaintext=b"msg-2")
        env5 = auth.seal(key, group_id="g1", sender="N1", sequence=5, plaintext=b"msg-5")

        # Out-of-order delivery: receive seq 2 first, then seq 1
        self.assertEqual(auth.open(key, SignedEnvelope.from_dict(env2.to_dict())), b"msg-2")
        self.assertEqual(auth.open(key, SignedEnvelope.from_dict(env1.to_dict())), b"msg-1")

        # Exact replay of seq 2 must be rejected
        with self.assertRaises(ValueError):
            auth.open(key, env2)

        # Forged packet with huge sequence number (seq=9999) and invalid signature
        # MUST NOT advance the replay window (DoS protection check)
        forged = SignedEnvelope(
            group_id="g1",
            sender="N1",
            sequence=9999,
            key_version=1,
            payload=env5.payload,
            signature=b"\x00" * 32,
        )
        with self.assertRaises(ValueError):
            auth.open(key, forged)

        # Legitimate seq 5 must still succeed because forged seq 9999 was not committed!
        self.assertEqual(auth.open(key, env5), b"msg-5")


class GroupServiceTests(unittest.TestCase):
    def test_group_creation_single_use_invitation_and_encrypted_messages(self) -> None:
        service = GroupService()
        group = service.create_group("  Рятувальна група  ")
        self.assertEqual(group["name"], "Рятувальна група")
        self.assertEqual(len(service.list_groups()), 1)

        invite = service.create_invitation(group["group_id"], "http://127.0.0.1:8765/")
        self.assertTrue(invite["token"])
        self.assertIn(invite["token"], invite["url"])

        joined = service.join_group(invite["token"])
        self.assertEqual(joined["group_id"], group["group_id"])
        with self.assertRaises(ValueError):
            service.join_group(invite["token"])

        sent = service.send_message(group["group_id"], "Олена", "Привіт, перевірка зв'язку!")
        self.assertEqual(sent["sender"], "Олена")
        self.assertEqual(sent["body"], "Привіт, перевірка зв'язку!")

        # Rotate group key and send a second message; both v1 and v2 messages remain readable
        rotated = service.rotate_group_key(group["group_id"])
        self.assertEqual(rotated["key_version"], 2)
        service.send_message(group["group_id"], "Богдан", "Ключ оновлено!")

        messages = service.list_messages(group["group_id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["body"], "Привіт, перевірка зв'язку!")
        self.assertEqual(messages[1]["body"], "Ключ оновлено!")

    def test_service_validation_and_bounds(self) -> None:
        service = GroupService(max_groups=1, max_messages_per_group=2, max_invitations=1)
        group = service.create_group("Alpha")
        with self.assertRaises(ValueError):
            service.create_group("Beta")
        with self.assertRaises(ValueError):
            service.create_group("   ")
        with self.assertRaises(KeyError):
            service.send_message("missing", "Alice", "hi")
        with self.assertRaises(ValueError):
            service.send_message(group["group_id"], "", "hi")
        with self.assertRaises(ValueError):
            service.send_message(group["group_id"], "Alice", "   ")

        first_invite = service.create_invitation(group["group_id"], "http://localhost")
        second_invite = service.create_invitation(group["group_id"], "http://localhost")
        with self.assertRaises(ValueError):
            service.join_group(first_invite["token"])
        self.assertEqual(service.join_group(second_invite["token"])["group_id"], group["group_id"])

        service.send_message(group["group_id"], "A", "m1")
        service.send_message(group["group_id"], "A", "m2")
        service.send_message(group["group_id"], "A", "m3")
        bodies = [m["body"] for m in service.list_messages(group["group_id"])]
        self.assertEqual(bodies, ["m2", "m3"])

    def test_invitation_tokens_are_unique_and_http_helpers_reject_bad_types(self) -> None:
        tokens = {generate_invitation_token() for _ in range(32)}
        self.assertEqual(len(tokens), 32)
        with self.assertRaises(TypeError):
            _require_str({"name": None}, "name")
        with self.assertRaises(TypeError):
            _require_str({"name": 123}, "name")
        with self.assertRaises(TypeError):
            _require_float({"x": True}, "x", 0.0)


if __name__ == "__main__":
    unittest.main()
