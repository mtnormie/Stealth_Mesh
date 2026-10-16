"""Tests for AES-256-GCM encryption, key generation, and encrypted group messaging."""

import unittest

from app.services.group_service import GroupService
from security.encryption import EncryptedPayload, decrypt, encrypt
from security.key_manager import generate_group_key, generate_invitation_token


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
        messages = service.list_messages(group["group_id"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["body"], "Привіт, перевірка зв'язку!")

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

    def test_invitation_tokens_are_unique(self) -> None:
        tokens = {generate_invitation_token() for _ in range(32)}
        self.assertEqual(len(tokens), 32)


if __name__ == "__main__":
    unittest.main()
