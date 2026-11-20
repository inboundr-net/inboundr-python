"""Request building and response handling shared by the sync and async clients."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

import httpx

from ._errors import InboundrAPIError, InboundrError, InboundrRateLimitError
from ._version import __version__

DEFAULT_BASE_URL = "https://inboundr.net"
API_KEY_ENV_VAR = "INBOUNDR_API_KEY"
DEFAULT_TIMEOUT = 30.0


def resolve_api_key(api_key: str | None) -> str:
    key = api_key or os.environ.get(API_KEY_ENV_VAR)
    if not key:
        raise InboundrError(
            f"No API key. Pass Inboundr(api_key=...) or set {API_KEY_ENV_VAR}. "
            "Create a key in the console under API keys."
        )
    return key


def base_api_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/v1"


def default_headers(api_key: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {api_key}",
        "accept": "application/json",
        "user-agent": f"inboundr-python/{__version__}",
    }


def segment(value: str | int) -> str:
    """Percent-encode one path segment. Ids are safe; email addresses are not."""
    return quote(str(value), safe="")


def clean_query(params: Any) -> dict[str, Any] | None:
    if not params:
        return None
    return {k: v for k, v in dict(params).items() if v is not None}


def _message(status: int, body: Any) -> str:
    if isinstance(body, dict) and "error" in body:
        error = body["error"]
        return error if isinstance(error, str) else f"{status} {json.dumps(error)}"
    if isinstance(body, str) and body.strip():
        return f"{status} {body}"
    return f"Request failed with status {status}"


def handle_response(response: httpx.Response, *, raw: bool = False) -> Any:
    request_id = response.headers.get("x-request-id")
    if response.is_success:
        if raw:
            return response.content
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    try:
        body: Any = response.json()
    except ValueError:
        body = response.text

    message = _message(response.status_code, body)
    if response.status_code == 429:
        header = response.headers.get("retry-after")
        try:
            retry_after: float | None = float(header) if header is not None else None
        except ValueError:
            retry_after = None
        if retry_after is not None and retry_after < 0:
            retry_after = None
        raise InboundrRateLimitError(
            message, status=429, body=body, request_id=request_id, retry_after_seconds=retry_after
        )
    raise InboundrAPIError(message, status=response.status_code, body=body, request_id=request_id)


def transport_error(method: str, path: str, exc: Exception, timeout: float | None) -> InboundrError:
    if isinstance(exc, httpx.TimeoutException):
        return InboundrError(f"{method} {path} timed out after {timeout}s.")
    return InboundrError(f"{method} {path} failed: {exc}")
