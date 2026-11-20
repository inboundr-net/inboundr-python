"""Python SDK for the Inboundr API.

::

    from inboundr import Inboundr, verify_webhook

    client = Inboundr()  # reads INBOUNDR_API_KEY
    page = client.emails.list({"direction": "inbound", "limit": 20})
"""

from ._async_client import AsyncInboundr
from ._base import API_KEY_ENV_VAR, DEFAULT_BASE_URL
from ._client import Inboundr
from ._errors import (
    InboundrAPIError,
    InboundrError,
    InboundrRateLimitError,
    InboundrSignatureError,
    SignatureFailureReason,
)
from ._types import *  # noqa: F403
from ._types import __all__ as _types_all
from ._version import __version__
from ._webhooks import (
    DEFAULT_TOLERANCE_SECONDS,
    DELIVERY_ID_HEADER,
    EMAIL_ID_HEADER,
    EVENT_HEADER,
    ID_SIGNATURE_HEADER,
    LEGACY_DELIVERY_ID_HEADER,
    LEGACY_SIGNATURE_HEADER,
    SIGNATURE_HEADER,
    WebhookHeaders,
    WebhookIds,
    read_webhook_headers,
    verify_webhook,
    verify_webhook_ids,
)

__all__ = [
    "API_KEY_ENV_VAR",
    "AsyncInboundr",
    "DEFAULT_BASE_URL",
    "DEFAULT_TOLERANCE_SECONDS",
    "DELIVERY_ID_HEADER",
    "EMAIL_ID_HEADER",
    "EVENT_HEADER",
    "ID_SIGNATURE_HEADER",
    "Inboundr",
    "InboundrAPIError",
    "InboundrError",
    "InboundrRateLimitError",
    "InboundrSignatureError",
    "LEGACY_DELIVERY_ID_HEADER",
    "LEGACY_SIGNATURE_HEADER",
    "SIGNATURE_HEADER",
    "SignatureFailureReason",
    "WebhookHeaders",
    "WebhookIds",
    "__version__",
    "read_webhook_headers",
    "verify_webhook",
    "verify_webhook_ids",
    *_types_all,
]
