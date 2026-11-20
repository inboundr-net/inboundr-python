![Inboundr](https://raw.githubusercontent.com/inboundr-net/inboundr-python/refs/heads/main/assets/banner.png)

# Inboundr Python SDK

[![PyPI](https://img.shields.io/pypi/v/inboundr?color=0f766e&label=pypi)](https://pypi.org/project/inboundr/)
[![license](https://img.shields.io/badge/license-MIT-0f766e)](./LICENSE)

Python library for the [Inboundr](https://inboundr.net) API: receive email over signed webhooks, read and reply to it, and manage domains, addresses and endpoints.

- [Quickstart](https://inboundr.net/docs/quickstart)
- [API reference](https://inboundr.net/docs/api-reference/introduction)
- [Verifying webhooks](https://inboundr.net/docs/webhooks/verifying-signatures)

## Install

```bash
pip install inboundr
```

Python 3.10+. Depends on `httpx`.

## Setup

Create an API key in the console under **API keys**, then:

```python
from inboundr import Inboundr

client = Inboundr("inb_123456789")
```

With no argument, the key is read from `INBOUNDR_API_KEY`.

## Receive email

Every inbound email is delivered to your endpoint as a signed `POST`. Verify it with the raw request body and the request's headers:

```python
from flask import Flask, request
from inboundr import InboundrSignatureError, verify_webhook

app = Flask(__name__)

@app.post("/inbound")
def inbound():
    try:
        event = verify_webhook(request.get_data(), request.headers, WEBHOOK_SECRET)
    except InboundrSignatureError:
        return "", 400

    email = event["email"]
    print(email["from"], email["subject"], email["text"])
    return "", 204
```

The secret is the `whsec_` value returned when you create the endpoint. Pass the body as bytes, exactly as received: parsing and re-serializing the JSON changes it and breaks the signature.

`request.headers` can be any headers object (Flask, Django, FastAPI/Starlette) or a plain dict.

### Retries

Failed deliveries are retried with the same delivery id. To skip deliveries you have already handled, verify with `verify_webhook_delivery`, which also checks the signature on the delivery id:

```python
from inboundr import verify_webhook_delivery

delivery = verify_webhook_delivery(request.get_data(), request.headers, WEBHOOK_SECRET)
if already_handled(delivery.delivery_id):
    return "", 204
email = delivery.event["email"]
```

Don't deduplicate on the `x-inboundr-delivery-id` header read directly: it isn't covered by the body's signature, so a replayed delivery could carry any id.

### Missing body

Some hosts drop the request body. The delivery still carries a signed email id, so you can fetch the email instead:

```python
from inboundr import verify_webhook_ids

# when verify_webhook raises with err.reason == "missing_body"
ids = verify_webhook_ids(request.headers, WEBHOOK_SECRET)
email = client.emails.get(ids.email_id)
```

### Failure reasons

`InboundrSignatureError.reason` is one of:

| Reason | Meaning |
| --- | --- |
| `missing_secret` | No secret was passed. |
| `missing_header` | No signature header. |
| `malformed_header` | The signature header can't be parsed. |
| `invalid_signature` | The signature doesn't match. |
| `timestamp_out_of_tolerance` | Signed more than 5 minutes ago (set `tolerance_seconds` to change). |
| `missing_body` | Signed, but the body is empty. |
| `invalid_payload` | Verified, but not a known event. |

## Read email

```python
page = client.emails.list({"direction": "inbound", "limit": 20})

email = client.emails.get(page["data"][0]["id"])
thread = client.threads.get(email["threadId"])
```

To go through every page:

```python
for email in client.emails.list_all({"direction": "inbound"}):
    print(email["subject"])
```

Requests and responses are plain dicts with the API's field names, typed with `TypedDict`.

## Reply and send

```python
client.emails.reply(email["id"], {"text": "Thanks, we're on it."})

client.emails.send({
    "from": "agent@yourdomain.com",
    "to": ["customer@example.com"],
    "subject": "Your order shipped",
    "html": "<p>It's on the way.</p>",
})
```

Sending needs a connected sender or a verified domain with sending enabled.

## Attachments

```python
# A signed URL, valid for 15 minutes
url = client.emails.attachment_url(email["id"], 0)["url"]

# Or the file itself
data = client.emails.download_attachment(email["id"], 0)
```

## Async

`AsyncInboundr` has the same methods:

```python
from inboundr import AsyncInboundr

async with AsyncInboundr() as client:
    page = await client.emails.list({"limit": 20})
    async for email in client.emails.list_all():
        ...
```

## Resources

| Resource | Methods |
| --- | --- |
| `emails` | `list`, `list_all`, `get`, `send`, `reply`, `delete`, `retry`, `attachment_url`, `download_attachment` |
| `threads` | `get` |
| `domains` | `list`, `create`, `get`, `update`, `delete` |
| `addresses` | `list`, `create`, `get`, `update`, `delete` |
| `endpoints` | `list`, `create`, `get`, `update`, `delete`, `test`, `deliveries`, `list_all_deliveries` |
| `shield_rules` | `list`, `create`, `get`, `update`, `delete`, `move`, `reorder` |
| `senders` | `list` |
| `suppressions` | `list`, `create`, `delete` |
| `forward_destinations` | `list`, `create`, `delete` |

See the [API reference](https://inboundr.net/docs/api-reference/introduction) for parameters and responses. All types are exported:

```python
from inboundr import Email, Endpoint, SendEmailParams
```

## Errors

| Error | Raised when | Attributes |
| --- | --- | --- |
| `InboundrAPIError` | The API returns a non-2xx status | `status`, `body`, `request_id` |
| `InboundrRateLimitError` | The API returns `429` | `retry_after_seconds` |
| `InboundrError` | The request fails or times out | |

```python
from inboundr import InboundrAPIError

try:
    client.domains.create({"domain": "example.com"})
except InboundrAPIError as err:
    print(err.status, err.body)
```

Requests are not retried automatically.

## Options

```python
client = Inboundr(
    "inb_123456789",
    base_url="https://inboundr.net",  # default
    timeout=30.0,                     # seconds, default; None disables it
    http_client=httpx.Client(),       # optional, your own client
)
```

With your own `http_client`, its timeout is used unless you also pass `timeout`.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

MIT
