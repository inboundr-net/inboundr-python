"""Errors raised by the SDK."""

from __future__ import annotations

from typing import Any, Literal

__all__ = [
    "InboundrError",
    "InboundrAPIError",
    "InboundrRateLimitError",
    "InboundrSignatureError",
    "SignatureFailureReason",
]


class InboundrError(Exception):
    """Base class for every error this package raises."""


class InboundrAPIError(InboundrError):
    """The API answered with a non-2xx status.

    `body` is the decoded JSON body, or the raw text when it wasn't JSON. A
    400's body holds the validation tree naming the field that failed.
    """

    def __init__(self, message: str, *, status: int, body: Any, request_id: str | None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.request_id = request_id


class InboundrRateLimitError(InboundrAPIError):
    """A 429. `retry_after_seconds` comes from the `retry-after` header."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        body: Any,
        request_id: str | None,
        retry_after_seconds: float | None,
    ) -> None:
        super().__init__(message, status=status, body=body, request_id=request_id)
        self.retry_after_seconds = retry_after_seconds


SignatureFailureReason = Literal[
    "missing_secret",
    "missing_header",
    "malformed_header",
    "invalid_signature",
    "timestamp_out_of_tolerance",
    "missing_body",
    "invalid_payload",
]


class InboundrSignatureError(InboundrError):
    """A webhook request that could not be verified. Respond with 400.

    `reason` is for logs. Don't use it to decide whether to trust a request:
    a forged one can choose its own failure.
    """

    def __init__(self, reason: SignatureFailureReason, message: str) -> None:
        super().__init__(message)
        self.reason: SignatureFailureReason = reason
