"""Unit tests for the standalone Diia + Military ID authentication module."""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest

from security.diia_military_auth import (
    AuthStatus,
    DiiaAuthAdapter,
    MilitaryIdVerifier,
    OperatorOnboardingGate,
    hash_tax_id,
)


class DiiaMilitaryAuthTests(unittest.TestCase):
    def test_diia_challenge_and_callback_verification(self) -> None:
        acquirer_secret = b"test-acquirer-secret-key-32bytes"
        salt = b"test-tax-id-salt-16b"
        adapter = DiiaAuthAdapter()
        challenge = adapter.create_challenge(ttl_seconds=120.0, now=1000.0)
        self.assertTrue(challenge.deep_link.startswith("https://diia.app/auth/stealth-mesh?"))

        subject_hash = hash_tax_id("1234567890", salt=salt)
        payload = {
            "request_id": challenge.request_id,
            "nonce": challenge.nonce,
            "subject_hash": subject_hash,
            "full_name": "Лещенко Матвій Павлович",
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        sig = hmac.new(acquirer_secret, blob, hashlib.sha256).hexdigest()

        claim = adapter.verify_callback(
            challenge,
            {**payload, "signature": sig},
            acquirer_secret=acquirer_secret,
            now=1050.0,
        )
        self.assertEqual(claim.status, AuthStatus.VERIFIED)
        self.assertEqual(claim.subject_hash, subject_hash)

        with self.assertRaises(PermissionError):
            adapter.verify_callback(
                challenge,
                {**payload, "signature": "0" * 64},
                acquirer_secret=acquirer_secret,
                now=1050.0,
            )

        with self.assertRaises(PermissionError):
            adapter.verify_callback(
                challenge,
                {**payload, "signature": sig},
                acquirer_secret=acquirer_secret,
                now=1200.0,
            )

    def test_military_id_offline_qr_verification_and_onboarding_gate(self) -> None:
        issuer_secret = b"test-military-issuer-secret-key!"
        acquirer_secret = b"test-acquirer-secret-key-32bytes"
        salt = b"test-tax-id-salt-16b"

        doc = MilitaryIdVerifier.issue_signed_document(
            document_number="ВК-847291",
            unit_code="А0001",
            service_status="active_duty",
            issuer_secret=issuer_secret,
            ttl_seconds=86400.0,
            now=2000.0,
        )
        qr = MilitaryIdVerifier.encode_qr_payload(doc)
        verified_doc = MilitaryIdVerifier.verify_qr_payload(qr, issuer_secret=issuer_secret, now=2500.0)
        self.assertEqual(verified_doc.document_number, "ВК-847291")
        self.assertEqual(verified_doc.unit_code, "А0001")

        tampered_qr = qr.replace("active_duty", "reserve")
        with self.assertRaises(PermissionError):
            MilitaryIdVerifier.verify_qr_payload(tampered_qr, issuer_secret=issuer_secret, now=2500.0)

        with self.assertRaises(PermissionError):
            MilitaryIdVerifier.verify_qr_payload(qr, issuer_secret=issuer_secret, now=95000.0)

        adapter = DiiaAuthAdapter()
        challenge = adapter.create_challenge(ttl_seconds=120.0, now=2000.0)
        subject_hash = hash_tax_id("0987654321", salt=salt)
        payload = {
            "request_id": challenge.request_id,
            "nonce": challenge.nonce,
            "subject_hash": subject_hash,
            "full_name": "Боєць Тестовий",
        }
        sig = hmac.new(
            acquirer_secret,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        claim = adapter.verify_callback(
            challenge,
            {**payload, "signature": sig},
            acquirer_secret=acquirer_secret,
            now=2050.0,
        )

        auth_pass = OperatorOnboardingGate.issue_operator_pass(claim, verified_doc, now=2100.0)
        self.assertEqual(auth_pass.status, AuthStatus.VERIFIED)
        self.assertEqual(auth_pass.unit_code, "А0001")
        self.assertEqual(auth_pass.document_number, "ВК-847291")

    def test_group_service_opt_in_operator_auth_gate(self) -> None:
        from app.services.group_service import GroupService

        issuer_secret = b"test-military-issuer-secret-key!"
        acquirer_secret = b"test-acquirer-secret-key-32bytes"
        salt = b"test-tax-id-salt-16b"

        svc = GroupService(require_operator_auth=True)
        with self.assertRaises(PermissionError):
            svc.create_group("CombatSquad")

        doc = MilitaryIdVerifier.issue_signed_document(
            document_number="ВК-100200",
            unit_code="A4010",
            service_status="active_duty",
            issuer_secret=issuer_secret,
        )
        adapter = DiiaAuthAdapter()
        ch = adapter.create_challenge()
        sub = hash_tax_id("1122334455", salt=salt)
        payload = {"request_id": ch.request_id, "nonce": ch.nonce, "subject_hash": sub, "full_name": "Оператор-1"}
        sig = hmac.new(
            acquirer_secret,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        claim = adapter.verify_callback(ch, {**payload, "signature": sig}, acquirer_secret=acquirer_secret)
        auth_pass = OperatorOnboardingGate.issue_operator_pass(claim, doc)
        reg = svc.register_operator_pass(auth_pass)
        self.assertTrue(reg["verified"])

        grp = svc.create_group("CombatSquad", operator_pass_id=auth_pass.pass_id)
        msg = svc.send_message(grp["group_id"], "Оператор-1", "Зв'язок перевірено", operator_pass_id=auth_pass.pass_id)
        self.assertEqual(msg["body"], "Зв'язок перевірено")


if __name__ == "__main__":
    unittest.main()
