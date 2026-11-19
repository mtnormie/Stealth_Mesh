"""Standalone Diia (Дія.Підпис) and Military ID (Військовий квиток / Резерв+) authentication module.

NOTE: This module is intentionally decoupled from ``app/main.py`` and ``GroupService``
so existing workflows and automated tests do not require interactive authentication.
Live government Diia APIs (``api2.diia.gov.ua``) and Oberih/Reserve+ registries require
official institutional accreditation, mTLS certificates, and online connectivity; this
module provides the cryptographic verification contracts and offline-capable QR payload
verification for pre-deployment operator onboarding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import hmac
import json
import secrets
import time
from typing import Mapping


class AuthStatus(str, Enum):
    """Lifecycle status of an identity or military document verification."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class DiiaAuthChallenge:
    """One-time cryptographic challenge for Diia app deep-link / QR authentication."""

    request_id: str
    nonce: str
    deep_link: str
    created_at: float
    expires_at: float


@dataclass(frozen=True, slots=True)
class DiiaIdentityClaim:
    """Verified identity claim returned after Diia.Підпис / OIDC callback validation."""

    subject_hash: str
    full_name: str
    verified_at: float
    status: AuthStatus = AuthStatus.VERIFIED


@dataclass(frozen=True, slots=True)
class MilitaryIdDocument:
    """Structured military service document (Військовий квиток / Резерв+ QR payload)."""

    document_number: str
    unit_code: str
    service_status: str
    issued_at: float
    expires_at: float
    issuer_signature: str


@dataclass(frozen=True, slots=True)
class OperatorAuthPass:
    """Combined pre-deployment authorization badge linking Diia + Military ID."""

    pass_id: str
    subject_hash: str
    full_name: str
    document_number: str
    unit_code: str
    issued_at: float
    expires_at: float
    status: AuthStatus = AuthStatus.VERIFIED


def hash_tax_id(rnokpp: str, *, salt: bytes) -> str:
    """Return a non-reversible SHA-256 digest of a citizen tax ID (РНОКПП) for privacy."""
    if not isinstance(rnokpp, str) or not rnokpp.strip().isdigit() or len(rnokpp.strip()) != 10:
        raise ValueError("rnokpp must be a 10-digit string")
    if not isinstance(salt, bytes) or len(salt) < 16:
        raise ValueError("salt must be at least 16 bytes")
    return hmac.new(salt, rnokpp.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def _canonical_doc_bytes(
    document_number: str,
    unit_code: str,
    service_status: str,
    issued_at: float,
    expires_at: float,
) -> bytes:
    payload = {
        "document_number": document_number,
        "unit_code": unit_code,
        "service_status": service_status,
        "issued_at": round(float(issued_at), 3),
        "expires_at": round(float(expires_at), 3),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class DiiaAuthAdapter:
    """Handles Diia challenge generation and cryptographic callback verification."""

    def __init__(self, *, deep_link_base: str = "https://diia.app/auth/stealth-mesh") -> None:
        if not isinstance(deep_link_base, str) or not deep_link_base.startswith("https://"):
            raise ValueError("deep_link_base must be an HTTPS URL")
        self._base = deep_link_base.rstrip("/")

    def create_challenge(
        self,
        *,
        ttl_seconds: float = 300.0,
        now: float | None = None,
    ) -> DiiaAuthChallenge:
        """Generate a one-time challenge and Diia deep-link URI."""
        if isinstance(ttl_seconds, bool) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        ts = time.time() if now is None else float(now)
        request_id = secrets.token_hex(16)
        nonce = secrets.token_urlsafe(24)
        deep_link = f"{self._base}?request_id={request_id}&nonce={nonce}"
        return DiiaAuthChallenge(
            request_id=request_id,
            nonce=nonce,
            deep_link=deep_link,
            created_at=ts,
            expires_at=ts + float(ttl_seconds),
        )

    def verify_callback(
        self,
        challenge: DiiaAuthChallenge,
        callback_payload: Mapping[str, object],
        *,
        acquirer_secret: bytes,
        now: float | None = None,
    ) -> DiiaIdentityClaim:
        """Verify a Diia callback response against the issued challenge and HMAC signature."""
        if not isinstance(acquirer_secret, bytes) or len(acquirer_secret) < 16:
            raise ValueError("acquirer_secret must be at least 16 bytes")
        ts = time.time() if now is None else float(now)
        if ts > challenge.expires_at:
            raise PermissionError("Diia authentication challenge expired")

        req_id = str(callback_payload.get("request_id", ""))
        nonce = str(callback_payload.get("nonce", ""))
        subject_hash = str(callback_payload.get("subject_hash", "")).strip()
        full_name = str(callback_payload.get("full_name", "")).strip()
        provided_sig = str(callback_payload.get("signature", "")).strip()

        if not hmac.compare_digest(req_id, challenge.request_id):
            raise PermissionError("request_id mismatch")
        if not hmac.compare_digest(nonce, challenge.nonce):
            raise PermissionError("nonce mismatch")
        if len(subject_hash) != 64 or not full_name:
            raise ValueError("callback_payload missing valid subject_hash or full_name")

        signed_blob = json.dumps(
            {
                "request_id": req_id,
                "nonce": nonce,
                "subject_hash": subject_hash,
                "full_name": full_name,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        expected_sig = hmac.new(acquirer_secret, signed_blob, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise PermissionError("invalid Diia callback signature")

        return DiiaIdentityClaim(
            subject_hash=subject_hash,
            full_name=full_name,
            verified_at=ts,
            status=AuthStatus.VERIFIED,
        )


class MilitaryIdVerifier:
    """Offline-capable verifier for signed Military ID (Військовий квиток / Резерв+) QR payloads."""

    ALLOWED_STATUSES = frozenset({"active_duty", "reserve", "contract"})

    @staticmethod
    def issue_signed_document(
        *,
        document_number: str,
        unit_code: str,
        service_status: str,
        issuer_secret: bytes,
        ttl_seconds: float = 86400.0 * 30,
        now: float | None = None,
    ) -> MilitaryIdDocument:
        """Create a signed MilitaryIdDocument (intended for controlled test/issuer fixtures)."""
        if not isinstance(issuer_secret, bytes) or len(issuer_secret) < 16:
            raise ValueError("issuer_secret must be at least 16 bytes")
        doc_num = document_number.strip()
        unit = unit_code.strip()
        status = service_status.strip()
        if not doc_num or not unit:
            raise ValueError("document_number and unit_code must be non-empty")
        if status not in MilitaryIdVerifier.ALLOWED_STATUSES:
            raise ValueError(f"unsupported service_status: {status}")
        ts = time.time() if now is None else float(now)
        expires_at = ts + float(ttl_seconds)
        raw = _canonical_doc_bytes(doc_num, unit, status, ts, expires_at)
        sig = hmac.new(issuer_secret, raw, hashlib.sha256).hexdigest()
        return MilitaryIdDocument(
            document_number=doc_num,
            unit_code=unit,
            service_status=status,
            issued_at=ts,
            expires_at=expires_at,
            issuer_signature=sig,
        )

    @staticmethod
    def encode_qr_payload(doc: MilitaryIdDocument) -> str:
        """Serialize a MilitaryIdDocument into a compact JSON QR string."""
        return json.dumps(
            {
                "document_number": doc.document_number,
                "unit_code": doc.unit_code,
                "service_status": doc.service_status,
                "issued_at": doc.issued_at,
                "expires_at": doc.expires_at,
                "issuer_signature": doc.issuer_signature,
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def verify_qr_payload(
        cls,
        raw_qr: str,
        *,
        issuer_secret: bytes,
        now: float | None = None,
    ) -> MilitaryIdDocument:
        """Parse and cryptographically verify a Military ID QR payload offline."""
        if not isinstance(raw_qr, str) or not raw_qr.strip():
            raise ValueError("raw_qr must be a non-empty string")
        if not isinstance(issuer_secret, bytes) or len(issuer_secret) < 16:
            raise ValueError("issuer_secret must be at least 16 bytes")

        try:
            data = json.loads(raw_qr)
        except json.JSONDecodeError as exc:
            raise ValueError("malformed Military ID QR payload") from exc
        if not isinstance(data, dict):
            raise ValueError("Military ID QR payload must be a JSON object")

        doc_num = str(data.get("document_number", "")).strip()
        unit = str(data.get("unit_code", "")).strip()
        status = str(data.get("service_status", "")).strip()
        sig = str(data.get("issuer_signature", "")).strip()
        try:
            issued_at = float(data["issued_at"])
            expires_at = float(data["expires_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("missing or invalid timestamps in Military ID payload") from exc

        if not doc_num or not unit:
            raise ValueError("document_number and unit_code are required")
        if status not in cls.ALLOWED_STATUSES:
            raise PermissionError(f"ineligible military service_status: {status}")

        ts = time.time() if now is None else float(now)
        if ts > expires_at or issued_at > expires_at:
            raise PermissionError("Military ID document expired")

        raw = _canonical_doc_bytes(doc_num, unit, status, issued_at, expires_at)
        expected_sig = hmac.new(issuer_secret, raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            raise PermissionError("invalid Military ID issuer signature")

        return MilitaryIdDocument(
            document_number=doc_num,
            unit_code=unit,
            service_status=status,
            issued_at=issued_at,
            expires_at=expires_at,
            issuer_signature=sig,
        )


class OperatorOnboardingGate:
    """Combines Diia identity verification and Military ID verification into an onboarding pass."""

    @staticmethod
    def issue_operator_pass(
        diia_claim: DiiaIdentityClaim,
        military_doc: MilitaryIdDocument,
        *,
        pass_ttl_seconds: float = 43200.0,
        now: float | None = None,
    ) -> OperatorAuthPass:
        """Issue a time-bounded operator pass only when both Diia and Military ID are verified."""
        if diia_claim.status != AuthStatus.VERIFIED:
            raise PermissionError("Diia identity claim is not verified")
        ts = time.time() if now is None else float(now)
        if ts > military_doc.expires_at:
            raise PermissionError("Military ID document is expired")
        if isinstance(pass_ttl_seconds, bool) or pass_ttl_seconds <= 0:
            raise ValueError("pass_ttl_seconds must be positive")
        return OperatorAuthPass(
            pass_id=secrets.token_hex(12),
            subject_hash=diia_claim.subject_hash,
            full_name=diia_claim.full_name,
            document_number=military_doc.document_number,
            unit_code=military_doc.unit_code,
            issued_at=ts,
            expires_at=min(ts + float(pass_ttl_seconds), military_doc.expires_at),
            status=AuthStatus.VERIFIED,
        )
