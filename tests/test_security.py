"""Tests for AES-256-GCM encryption, HKDF, HMAC, replay protection, and group messaging."""

import unittest

from app.main import _require_float, _require_str
from app.services.group_service import GroupService
from app.services.message_service import MeshMessageService
from app.services.status_service import NetworkSandboxService
from app.ui.settings_view import PWA_MANIFEST_JSON, render_qr_svg
from monitoring.jammer_locator import StealthLocationRegistry
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

        # Rotate group key 10 times (exceeding max_retained_key_versions=8) and verify messages stay readable
        for expected_ver in range(2, 12):
            rotated = service.rotate_group_key(group["group_id"])
            self.assertEqual(rotated["key_version"], expected_ver)
        service.send_message(group["group_id"], "Богдан", "Ключ оновлено!")

        messages = service.list_messages(group["group_id"])
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["body"], "Привіт, перевірка зв'язку!")
        self.assertEqual(messages[1]["body"], "Ключ оновлено!")
        # Verify signed_envelope of message[0] was also re-sealed and parses cleanly
        wire_bytes_0 = service.get_encrypted_wire_bytes(group["group_id"], messages[0]["id"])
        self.assertIn(b'"key_version":', wire_bytes_0)
        self.assertTrue(service.verify_member_token(group["group_id"], group["member_token"]))
        self.assertTrue(service.verify_member_token(group["group_id"], joined["member_token"]))
        self.assertFalse(service.verify_member_token(group["group_id"], "invalid-token"))

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

    def test_pwa_qr_svg_and_mesh_message_service_dispatch(self) -> None:
        svg = render_qr_svg("http://192.168.4.1:8765/?join=test-token-12345")
        self.assertIn("<svg", svg)
        self.assertIn("<rect", svg)
        self.assertIn('"standalone"', PWA_MANIFEST_JSON)

        groups = GroupService()
        sandbox = NetworkSandboxService(seed=42)
        bridge = MeshMessageService(groups, sandbox)
        grp = groups.create_group("Field Team")
        dispatched = bridge.dispatch_group_message(
            grp["group_id"],
            "Alpha",
            "Координати точки збору",
        )
        self.assertEqual(dispatched["body"], "Координати точки збору")
        self.assertGreater(int(dispatched["wire_bytes"]), 20)  # type: ignore[arg-type]
        self.assertIn("mesh_delivery", dispatched)
        wire_payload = groups.get_encrypted_wire_bytes(grp["group_id"], str(dispatched["id"]))
        self.assertNotIn("Координати точки збору".encode("utf-8"), wire_payload)

        # Also test a large 3500-char UTF-8 message to ensure no wire truncation occurs
        long_text = "Увага! " * 500
        long_dispatched = bridge.dispatch_group_message(grp["group_id"], "Alpha", long_text)
        long_wire = groups.get_encrypted_wire_bytes(grp["group_id"], str(long_dispatched["id"]))
        parsed_env = SignedEnvelope.from_dict(__import__("json").loads(long_wire.decode("utf-8")))
        self.assertEqual(parsed_env.sender, "Alpha")

    def test_stealth_location_registry_one_time_encrypted_beacon_and_lock(self) -> None:
        registry = StealthLocationRegistry()
        beacon1 = registry.create_one_time_beacon("N1", 330.0, 120.0)
        beacon2 = registry.create_one_time_beacon("N2", 330.0, 120.0)

        # Random blinding salt + nonce ensure identical coordinates produce distinct ciphertexts
        self.assertNotEqual(beacon1.payload.ciphertext, beacon2.payload.ciphertext)
        # Per-node keys are isolated
        self.assertNotEqual(registry.derive_node_beacon_key("N1"), registry.derive_node_beacon_key("N2"))

        # Compromising N1's key cannot forge a valid beacon for N3
        forged_n3 = registry.create_one_time_beacon(
            "N3", 500.0, 500.0, node_key=registry.derive_node_beacon_key("N1")
        )
        with self.assertRaises(ValueError):
            registry.register_beacon(forged_n3)

        coords = registry.register_beacon(beacon1)
        self.assertEqual(coords, (330.0, 120.0))
        self.assertTrue(registry.is_locked("N1"))

        # Second attempt to overwrite a locked node's location must be rejected
        later_beacon = registry.create_one_time_beacon("N1", 900.0, 900.0)
        with self.assertRaises(ValueError):
            registry.register_beacon(later_beacon)

        # Admin relock explicitly allowed when moving node in sandbox
        updated = registry.register_beacon(later_beacon, allow_admin_relock=True)
        self.assertEqual(updated, (900.0, 900.0))

        # After reset_all(), sequence=1 from N1 is accepted cleanly again
        registry.reset_all()
        fresh_beacon = registry.create_one_time_beacon("N1", 110.0, 260.0)
        self.assertEqual(fresh_beacon.sequence, 1)
        self.assertEqual(registry.register_beacon(fresh_beacon), (110.0, 260.0))

    def test_hardware_node_bridge_ingests_lora_messages_and_neighbors(self) -> None:
        from radio.hardware_bridge import HardwareNodeBridge

        groups = GroupService()
        groups.ensure_group("mesh-default", "Тактичний ефір Mesh (868 МГц)")
        sandbox = NetworkSandboxService(seed=42)
        hw = HardwareNodeBridge(groups, sandbox)

        hw._handle_serial_line("[StealthMesh] Node: N-A1B2 | SX1276: OK (0x12) | Neighbors: 1")
        hw._handle_serial_line('{"event":"beacon","src":"N-C3D4","hops":2,"rssi":-69,"snr":8.5}')
        hw._handle_serial_line(
            '{"event":"rx","src":"N-C3D4","dst":"BROADCAST","group":"mesh-default","sender":"Боєць-2","id":"N-C3D4-m1","hops":2,"rssi":-68,"snr":9.0,"msg":"Бачу ціль за посадкою"}'
        )
        # Duplicate frame ID must be ignored
        hw._handle_serial_line(
            '{"event":"rx","src":"N-C3D4","dst":"BROADCAST","group":"mesh-default","sender":"Боєць-2","id":"N-C3D4-m1","hops":2,"rssi":-68,"snr":9.0,"msg":"Бачу ціль за посадкою"}'
        )

        st = hw.get_status()
        self.assertEqual(st["gateway_node_id"], "N-A1B2")
        self.assertTrue(st["radio_ok"])
        self.assertEqual(len(st["neighbors"]), 1)  # type: ignore[arg-type]
        self.assertEqual(st["neighbors"][0]["node_id"], "N-C3D4")  # type: ignore[index]
        self.assertEqual(st["neighbors"][0]["hops"], 2)  # type: ignore[index]

        msgs = groups.list_messages("mesh-default")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["sender"], "Боєць-2")
        self.assertEqual(msgs[0]["body"], "Бачу ціль за посадкою")
        self.assertEqual(msgs[0].get("source_node"), "N-C3D4")
        self.assertEqual(msgs[0].get("hops"), 2)
        self.assertEqual(msgs[0].get("rssi"), -68)

    def test_tactical_mobile_app_view_zero_wifi_and_usb_c_support(self) -> None:
        from pathlib import Path
        import zipfile
        from app.ui.mobile_app_view import MOBILE_APP_HTML

        self.assertIn("0 мВт Wi-Fi/BT", MOBILE_APP_HTML)
        self.assertIn("ПІДКЛЮЧИТИ НОДУ ПО КАБЕЛЮ USB-C", MOBILE_APP_HTML)
        self.assertIn("CONNECT NODE VIA USB-C CABLE", MOBILE_APP_HTML)
        self.assertIn("AndroidUsbBridge", MOBILE_APP_HTML)
        self.assertIn("navigator.serial", MOBILE_APP_HTML)
        self.assertIn("SEND|mesh-default|", MOBILE_APP_HTML)

        apk_path = Path(__file__).resolve().parent.parent / "mobile_app" / "StealthMesh_Tactical_UA_EN.apk"
        self.assertTrue(apk_path.is_file())
        raw_apk = apk_path.read_bytes()
        self.assertIn(b"APK Sig Block 42", raw_apk)
        with zipfile.ZipFile(apk_path, "r") as zf:
            names = set(zf.namelist())
            self.assertIn("AndroidManifest.xml", names)
            self.assertIn("resources.arsc", names)
            self.assertIn("classes.dex", names)
            self.assertIn("assets/index.html", names)
            self.assertIn("META-INF/CERT.RSA", names)

    def test_mia_quarantine_challenge_and_dead_mans_switch(self) -> None:
        from security.key_manager import DeadMansSwitch, KeyManager

        km = KeyManager(max_retained_versions=4)
        km.register_group("squad-1")
        v2 = km.rotate_group_key("squad-1", purge_previous=True)
        self.assertEqual(v2.version, 2)
        with self.assertRaises(KeyError):
            km.get_key("squad-1", 1)

        dms = DeadMansSwitch(default_ttl_seconds=60.0)
        dms.arm("squad-1", ttl_seconds=60.0, now=100.0)
        self.assertFalse(dms.check_and_enforce(km, "squad-1", now=120.0))
        dms.heartbeat("squad-1", now=120.0)
        self.assertFalse(dms.check_and_enforce(km, "squad-1", now=150.0))
        self.assertTrue(dms.check_and_enforce(km, "squad-1", now=180.0))
        with self.assertRaises(KeyError):
            km.active_key("squad-1")
        with self.assertRaises(PermissionError):
            dms.heartbeat("squad-1", now=185.0)

        service = GroupService()
        created = service.create_group("Alpha")
        gid = created["group_id"]
        service.send_message(gid, "Боєць-1", "Виходимо на точку")
        q = service.quarantine_member(gid, "Боєць-3", reason="MIA", challenge="Каштан-42", rotate_key=True)
        self.assertTrue(q["quarantined"])
        self.assertEqual(q["key_version"], 2)

        msg = service.send_message(gid, "Боєць-3", "Я на зв'язку, заберіть мене")
        self.assertTrue(msg.get("quarantined"))
        self.assertEqual(msg.get("trust_status"), "quarantined_mia")

        with self.assertRaises(PermissionError):
            service.release_quarantine(gid, "Боєць-3", challenge_response="невірний-код")
        released = service.release_quarantine(gid, "Боєць-3", challenge_response="Каштан-42")
        self.assertFalse(released["quarantined"])
        self.assertTrue(released["verified"])

    def test_duress_wipe_clears_keys_and_history(self) -> None:
        service = GroupService()
        created = service.create_group("Bravo")
        gid = created["group_id"]
        service.send_message(gid, "Командир", "Секретний маршрут")
        wiped = service.trigger_duress_wipe(gid)
        self.assertTrue(wiped["duress_wiped"])
        self.assertTrue(wiped["sos_only_mode"])
        self.assertEqual(service.list_messages(gid), [])
        with self.assertRaises(PermissionError):
            service.send_message(gid, "Ворог", "Спроба запису")

    def test_ssrf_serial_validation_and_nonfinite_float_rejection(self) -> None:
        from app.main import _require_float
        from app.services.status_service import NetworkSandboxService
        from radio.hardware_bridge import HardwareNodeBridge

        bridge = HardwareNodeBridge(GroupService(), NetworkSandboxService())
        for bad_url in (
            "http://169.254.169.254/latest/meta-data",
            "https://8.8.8.8/dns",
            "http://user:pass@127.0.0.1:8765",
        ):
            with self.assertRaises(ValueError):
                bridge.configure_connection(http_node_url=bad_url)

        for bad_port in ("../../etc/passwd", "/tmp/evil;rm -rf /"):
            with self.assertRaises(ValueError):
                bridge.configure_connection(serial_port=bad_port)

        ok = bridge.configure_connection(serial_port="/dev/ttyACM0", http_node_url="http://192.168.4.1")
        self.assertEqual(ok["http_node_url"], "http://192.168.4.1")

        for nonfinite in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                _require_float({"x": nonfinite}, "x", 10.0)


if __name__ == "__main__":
    unittest.main()
