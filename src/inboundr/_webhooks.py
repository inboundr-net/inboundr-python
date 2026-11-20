"""Webhook signature verification.

Every delivery carries `x-inboundr-signature: t=<unix>,v1=<hex>`, where v1 is
HMAC-SHA256(secret, f"{t}.{raw_body}"). A second header,
`x-inboundr-id-signature`, signs f"ids.{t}.{delivery_id}.{email_id}" with the
same secret, for deliveries whose body was dropped on the way in. The legacy
`x-inbound-*` names carry identical values and are read as a fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, Union, cast

from ._errors import InboundrSignatureError
from ._types import EmailReceivedEvent

__all__ = [
    "SIGNATURE_HEADER",
    "EVENT_HEADER",
    "DELIVERY_ID_HEADER",
    "EMAIL_ID_HEADER",
    "ID_SIGNATURE_HEADER",
    "LEGACY_SIGNATURE_HEADER",
    "LEGACY_DELIVERY_ID_HEADER",
    "DEFAULT_TOLERANCE_SECONDS",
    "WebhookHeaders",
    "WebhookIds",
    "read_webhook_headers",
    "verify_webhook",
    "verify_webhook_ids",
]

SIGNATURE_HEADER = "x-inboundr-signature"
EVENT_HEADER = "x-inboundr-event"
DELIVERY_ID_HEADER = "x-inboundr-delivery-id"
EMAIL_ID_HEADER = "x-inboundr-email-id"
ID_SIGNATURE_HEADER = "x-inboundr-id-signature"
LEGACY_SIGNATURE_HEADER = "x-inbound-signature"
LEGACY_DELIVERY_ID_HEADER = "x-inbound-delivery-id"
LEGACY_EVENT_HEADER = "x-inbound-event"

DEFAULT_TOLERANCE_SECONDS = 300


class _HasGet(Protocol):
    def get(self, key: str, /) -> Any: ...


# Flask/Django/Starlette headers, `request.headers` objects in general, or a
# plain dict (matched case-insensitively).
HeadersLike = Union[Mapping[str, str], _HasGet]


@dataclass(frozen=True)
class WebhookHeaders:
    """The delivery headers, legacy spellings already folded in."""

    signature: str | None
    id_signature: str | None
    delivery_id: str | None
    email_id: str | None
    event: str | None


@dataclass(frozen=True)
class WebhookIds:
    delivery_id: str
    email_id: str


def _text(value: Any) -> str:
    # Raw ASGI headers are bytes; HTTP header bytes are latin-1 by definition.
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("latin-1")
    return str(value)


def _header_getter(headers: HeadersLike) -> Callable[[str], str | None]:
    if isinstance(headers, Mapping):
        lowered = {_text(k).lower(): v for k, v in headers.items()}

        def get(name: str) -> str | None:
            value = lowered.get(name)
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            return None if value is None else _text(value)

        return get

    def get_any(name: str) -> str | None:
        value = headers.get(name)
        return None if value is None else _text(value)

    return get_any


def read_webhook_headers(headers: HeadersLike) -> WebhookHeaders:
    """Read the delivery headers, preferring `x-inboundr-*` over the legacy names.

    Use it for the delivery id when deduplicating retries::

        delivery_id = read_webhook_headers(request.headers).delivery_id
    """
    get = _header_getter(headers)
    return WebhookHeaders(
        signature=get(SIGNATURE_HEADER) or get(LEGACY_SIGNATURE_HEADER),
        id_signature=get(ID_SIGNATURE_HEADER),
        delivery_id=get(DELIVERY_ID_HEADER) or get(LEGACY_DELIVERY_ID_HEADER),
        email_id=get(EMAIL_ID_HEADER),
        event=get(EVENT_HEADER) or get(LEGACY_EVENT_HEADER),
    )


_HEX = re.compile(r"^[0-9a-fA-F]+$")
# Unix seconds. Bounded so an attacker can't make int() parse thousands of
# digits (Python refuses past 4300 with a plain ValueError, not ours).
_DIGITS = re.compile(r"^[0-9]{1,15}$")


def _parse_signature(header: str) -> tuple[int, list[str]] | None:
    timestamp: int | None = None
    macs: list[str] = []
    for part in header.split(","):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if key == "t":
            if not _DIGITS.match(value):
                return None
            timestamp = int(value)
        elif key == "v1" and _HEX.match(value):
            macs.append(value.lower())
    if timestamp is None or not macs:
        return None
    return timestamp, macs


def _require_secret(secret: str) -> None:
    if not secret:
        raise InboundrSignatureError(
            "missing_secret",
            "No signing secret was provided. It is the whsec_ value returned when "
            "the endpoint was created.",
        )


def _require_header(value: str | None, name: str) -> str:
    if not value:
        raise InboundrSignatureError(
            "missing_header",
            f"Request has no {name} header. If you are behind a proxy, check that it forwards it.",
        )
    return value


def _verify_mac(
    header: str,
    name: str,
    secret: str,
    message: Callable[[int], bytes],
    tolerance_seconds: float,
    now: Callable[[], float] | None,
) -> None:
    parsed = _parse_signature(header)
    if parsed is None:
        raise InboundrSignatureError(
            "malformed_header", f'Could not parse the {name} header. Expected "t=<unix>,v1=<hex>".'
        )
    timestamp, macs = parsed
    expected = hmac.new(secret.encode(), message(timestamp), hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(mac, expected) for mac in macs):
        raise InboundrSignatureError(
            "invalid_signature",
            "Webhook signature did not match. Check the endpoint's secret, and pass the "
            "raw request body rather than re-serialized JSON.",
        )
    age = abs((now() if now else time.time()) - timestamp)
    if age > tolerance_seconds:
        raise InboundrSignatureError(
            "timestamp_out_of_tolerance",
            f"Webhook signature is valid but was made {int(age)}s ago, outside the "
            f"{tolerance_seconds:g}s window. Check this machine's clock.",
        )


def _signature_from(signature: str | HeadersLike | None) -> str | None:
    if signature is None or isinstance(signature, str):
        return signature
    return read_webhook_headers(signature).signature


def verify_webhook(
    payload: bytes | bytearray | memoryview | str,
    signature: str | HeadersLike | None,
    secret: str,
    *,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
    now: Callable[[], float] | None = None,
) -> EmailReceivedEvent:
    """Verify a delivery and return the event.

    `payload` is the raw request body, as bytes (or bytearray/memoryview) or text. `signature` is the
    request's headers (any mapping or headers object) or the signature header's
    value. Raises `InboundrSignatureError` if the request can't be verified.
    """
    _require_secret(secret)
    header = _require_header(_signature_from(signature), SIGNATURE_HEADER)
    if isinstance(payload, str):
        body = payload.encode()
    elif isinstance(payload, (bytes, bytearray, memoryview)):
        body = bytes(payload)
    else:
        raise TypeError(
            f"payload must be the raw request body as bytes or str, not {type(payload).__name__}"
        )
    if not body:
        raise InboundrSignatureError(
            "missing_body",
            "The request has a signature but an empty body; the host may have dropped it. "
            "Use verify_webhook_ids and fetch the email with client.emails.get(email_id).",
        )
    _verify_mac(header, SIGNATURE_HEADER, secret, lambda t: f"{t}.".encode() + body, tolerance_seconds, now)
    try:
        event = json.loads(body)
    except ValueError as exc:
        raise InboundrSignatureError("invalid_payload", f"Webhook body is not valid JSON: {exc}") from exc
    if not isinstance(event, dict) or event.get("event") != "email.received" or not isinstance(event.get("email"), dict):
        raise InboundrSignatureError(
            "invalid_payload", "Webhook body is not an event this version of the SDK knows."
        )
    return cast(EmailReceivedEvent, event)


def verify_webhook_ids(
    headers: HeadersLike,
    secret: str,
    *,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
    now: Callable[[], float] | None = None,
) -> WebhookIds:
    """Verify the id signature of a delivery whose body was dropped.

    It proves only that Inboundr sent a delivery naming this email, so the one
    safe use of the result is fetching the email through the API.
    """
    _require_secret(secret)
    read = read_webhook_headers(headers)
    if not read.delivery_id or not read.email_id:
        raise InboundrSignatureError(
            "missing_header", f"Request is missing {DELIVERY_ID_HEADER} or {EMAIL_ID_HEADER}."
        )
    header = _require_header(read.id_signature, ID_SIGNATURE_HEADER)
    delivery_id, email_id = read.delivery_id, read.email_id
    _verify_mac(
        header,
        ID_SIGNATURE_HEADER,
        secret,
        lambda t: f"ids.{t}.{delivery_id}.{email_id}".encode(),
        tolerance_seconds,
        now,
    )
    return WebhookIds(delivery_id=delivery_id, email_id=email_id)
