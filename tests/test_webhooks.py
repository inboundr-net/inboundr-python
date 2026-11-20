"""Webhook verification, cross-checked against an independent signer.

The signing scheme, which the platform implements in another repository:

    signature    = "t=" + <unix> + ",v1=" + hex(hmac_sha256(secret, f"{unix}.{raw_body}"))
    id signature = "t=" + <unix> + ",v1=" + hex(hmac_sha256(secret, f"ids.{unix}.{delivery_id}.{email_id}"))

carried in `x-inboundr-signature` (also the legacy `x-inbound-signature`) and
`x-inboundr-id-signature`. `sign` and `sign_ids` below implement it on their
own, so a passing case means the SDK and the spec agree, not that the SDK
agrees with itself. Changing the scheme is a breaking change.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from inboundr import (
    DEFAULT_TOLERANCE_SECONDS,
    DELIVERY_ID_HEADER,
    EMAIL_ID_HEADER,
    ID_SIGNATURE_HEADER,
    LEGACY_DELIVERY_ID_HEADER,
    LEGACY_SIGNATURE_HEADER,
    SIGNATURE_HEADER,
    InboundrSignatureError,
    read_webhook_headers,
    verify_webhook,
    verify_webhook_ids,
)

SECRET = "whsec_HXK9y2sVQ4mZ1pTn8LrJdCwB"
NOW = 1_770_000_000
EVENT = {
    "event": "email.received",
    "email": {
        "id": "em_7Kq2mR",
        "threadId": "thr_9Fj4nP",
        "messageId": "<CAF=abc123@mail.example.com>",
        "from": "customer@example.com",
        "to": ["agent@mail.example.com"],
        "cc": [],
        "recipients": ["agent@mail.example.com"],
        "subject": "Re: invoice 4471",
        "text": "Any update on this?",
        "html": None,
        "attachments": [],
        "verdicts": {"spam": "PASS", "spf": "PASS", "dkim": "PASS"},
        "receivedAt": "2026-02-02T03:20:00.000Z",
    },
}
BODY = json.dumps(EVENT).encode()
DELIVERY_ID, EMAIL_ID = "del_4hQx8w", "em_7Kq2mR"


def sign(secret: str, body: bytes, t: int) -> str:
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def sign_ids(secret: str, t: int, delivery_id: str, email_id: str) -> str:
    mac = hmac.new(secret.encode(), f"ids.{t}.{delivery_id}.{email_id}".encode(), hashlib.sha256).hexdigest()
    return f"t={t},v1={mac}"


def now() -> float:
    return float(NOW)


def rejects(reason: str, fn) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InboundrSignatureError) as info:
        fn()
    assert info.value.reason == reason


# --- valid signatures ---------------------------------------------------------


def test_a_signature_from_the_spec_verifies() -> None:
    event = verify_webhook(BODY, sign(SECRET, BODY, NOW), SECRET, now=now)
    assert event["email"]["id"] == "em_7Kq2mR"
    assert event["email"]["subject"] == "Re: invoice 4471"


def test_text_body_and_non_ascii_verify_as_utf8_bytes() -> None:
    body = json.dumps({**EVENT, "email": {**EVENT["email"], "subject": "請求書 📎"}}, ensure_ascii=False)
    event = verify_webhook(body, sign(SECRET, body.encode(), NOW), SECRET, now=now)
    assert event["email"]["subject"] == "請求書 📎"


def test_headers_mapping_is_read_case_insensitively() -> None:
    headers = {"X-Inboundr-Signature": sign(SECRET, BODY, NOW), "Content-Type": "application/json"}
    assert verify_webhook(BODY, headers, SECRET, now=now)["event"] == "email.received"


def test_legacy_signature_header_is_a_fallback() -> None:
    headers = {LEGACY_SIGNATURE_HEADER: sign(SECRET, BODY, NOW)}
    assert verify_webhook(BODY, headers, SECRET, now=now)["email"]["id"] == "em_7Kq2mR"


def test_canonical_header_wins_over_legacy() -> None:
    headers = {SIGNATURE_HEADER: sign(SECRET, BODY, NOW), LEGACY_SIGNATURE_HEADER: "t=1,v1=00"}
    verify_webhook(BODY, headers, SECRET, now=now)


def test_headers_object_with_get_is_accepted() -> None:
    class FrameworkHeaders:  # e.g. Starlette/Werkzeug: .get, case-insensitive, not a dict
        def __init__(self, values: dict[str, str]) -> None:
            self._values = {k.lower(): v for k, v in values.items()}

        def get(self, key: str) -> str | None:
            return self._values.get(key.lower())

    verify_webhook(BODY, FrameworkHeaders({SIGNATURE_HEADER: sign(SECRET, BODY, NOW)}), SECRET, now=now)


def test_several_v1_values_pass_if_any_matches() -> None:
    good = sign(SECRET, BODY, NOW).split("v1=")[1]
    verify_webhook(BODY, f"t={NOW},v1={'0' * 64},v1={good}", SECRET, now=now)


def test_uppercase_hex_and_extra_fields_are_tolerated() -> None:
    t, mac = NOW, sign(SECRET, BODY, NOW).split("v1=")[1]
    verify_webhook(BODY, f" t={t} , v0=abc , v1={mac.upper()} ", SECRET, now=now)


# --- rejections ---------------------------------------------------------------


def test_tampered_body_is_rejected() -> None:
    header = sign(SECRET, BODY, NOW)
    rejects("invalid_signature", lambda: verify_webhook(BODY.replace(b"4471", b"4472"), header, SECRET, now=now))


def test_another_endpoints_secret_is_rejected() -> None:
    rejects("invalid_signature", lambda: verify_webhook(BODY, sign("whsec_other", BODY, NOW), SECRET, now=now))


def test_reserialized_json_breaks_verification() -> None:
    header = sign(SECRET, BODY, NOW)
    reserialized = json.dumps(json.loads(BODY), indent=2).encode()
    rejects("invalid_signature", lambda: verify_webhook(reserialized, header, SECRET, now=now))


def test_the_timestamp_is_covered_by_the_signature() -> None:
    mac = sign(SECRET, BODY, NOW).split("v1=")[1]
    rejects("invalid_signature", lambda: verify_webhook(BODY, f"t={NOW + 1},v1={mac}", SECRET, now=now))


def test_stale_and_future_signatures_are_rejected() -> None:
    old = NOW - DEFAULT_TOLERANCE_SECONDS - 1
    future = NOW + DEFAULT_TOLERANCE_SECONDS + 1
    rejects("timestamp_out_of_tolerance", lambda: verify_webhook(BODY, sign(SECRET, BODY, old), SECRET, now=now))
    rejects("timestamp_out_of_tolerance", lambda: verify_webhook(BODY, sign(SECRET, BODY, future), SECRET, now=now))


def test_tolerance_can_be_widened() -> None:
    old = NOW - 10_000
    verify_webhook(BODY, sign(SECRET, BODY, old), SECRET, now=now, tolerance_seconds=float("inf"))


def test_a_forgery_is_rejected_before_the_timestamp_is_judged() -> None:
    old = NOW - 10_000
    rejects("invalid_signature", lambda: verify_webhook(BODY, sign("whsec_other", BODY, old), SECRET, now=now))


def test_truncated_mac_is_not_a_prefix_match() -> None:
    header = sign(SECRET, BODY, NOW)[:-2]
    rejects("invalid_signature", lambda: verify_webhook(BODY, header, SECRET, now=now))


@pytest.mark.parametrize("header", ["garbage", f"t={NOW}", "v1=abc", f"t=12e5,v1={'a' * 64}", f"t={NOW},v1=xyz"])
def test_malformed_headers_are_rejected(header: str) -> None:
    rejects("malformed_header", lambda: verify_webhook(BODY, header, SECRET, now=now))


def test_missing_secret_is_reported_first() -> None:
    rejects("missing_secret", lambda: verify_webhook(b"", None, "", now=now))


def test_missing_header() -> None:
    rejects("missing_header", lambda: verify_webhook(BODY, None, SECRET, now=now))
    rejects("missing_header", lambda: verify_webhook(BODY, {}, SECRET, now=now))


def test_signed_empty_body_is_missing_body_but_unsigned_is_missing_header() -> None:
    rejects("missing_body", lambda: verify_webhook(b"", sign(SECRET, b"", NOW), SECRET, now=now))
    rejects("missing_header", lambda: verify_webhook(b"", {}, SECRET, now=now))


def test_signed_non_json_and_unknown_events_are_invalid_payload() -> None:
    rejects("invalid_payload", lambda: verify_webhook(b"not json", sign(SECRET, b"not json", NOW), SECRET, now=now))
    other = json.dumps({"event": "email.bounced", "email": {}}).encode()
    rejects("invalid_payload", lambda: verify_webhook(other, sign(SECRET, other, NOW), SECRET, now=now))


# --- the id signature -----------------------------------------------------------


def id_headers(**overrides: str) -> dict[str, str]:
    headers = {
        ID_SIGNATURE_HEADER: sign_ids(SECRET, NOW, DELIVERY_ID, EMAIL_ID),
        DELIVERY_ID_HEADER: DELIVERY_ID,
        EMAIL_ID_HEADER: EMAIL_ID,
    }
    headers.update(overrides)
    return headers


def test_verify_webhook_ids_returns_the_ids() -> None:
    ids = verify_webhook_ids(id_headers(), SECRET, now=now)
    assert (ids.delivery_id, ids.email_id) == (DELIVERY_ID, EMAIL_ID)


def test_verify_webhook_ids_falls_back_to_the_legacy_delivery_id() -> None:
    headers = id_headers()
    headers[LEGACY_DELIVERY_ID_HEADER] = headers.pop(DELIVERY_ID_HEADER)
    assert verify_webhook_ids(headers, SECRET, now=now).delivery_id == DELIVERY_ID


def test_an_id_signature_for_another_email_is_rejected() -> None:
    rejects("invalid_signature", lambda: verify_webhook_ids(id_headers(**{EMAIL_ID_HEADER: "em_other"}), SECRET, now=now))


def test_body_and_id_signatures_cannot_stand_in_for_each_other() -> None:
    forged = sign(SECRET, f"{DELIVERY_ID}.{EMAIL_ID}".encode(), NOW)
    rejects("invalid_signature", lambda: verify_webhook_ids(id_headers(**{ID_SIGNATURE_HEADER: forged}), SECRET, now=now))
    body = f"{DELIVERY_ID}.{EMAIL_ID}".encode()
    rejects("invalid_signature", lambda: verify_webhook(body, sign_ids(SECRET, NOW, DELIVERY_ID, EMAIL_ID), SECRET, now=now))


def test_missing_ids_are_missing_header() -> None:
    rejects("missing_header", lambda: verify_webhook_ids({ID_SIGNATURE_HEADER: "t=1,v1=00"}, SECRET, now=now))


def test_read_webhook_headers_folds_in_legacy_names() -> None:
    read = read_webhook_headers({LEGACY_SIGNATURE_HEADER: "sig", LEGACY_DELIVERY_ID_HEADER: "del_1", "X-Inboundr-Email-Id": "em_1"})
    assert (read.signature, read.delivery_id, read.email_id) == ("sig", "del_1", "em_1")
