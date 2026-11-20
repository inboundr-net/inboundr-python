"""Checked by `mypy` (strict), never run. Each block is real usage. The lines
marked `# type: ignore[...]` must be errors: strict mypy reports an ignore
that isn't needed, so a type that stops rejecting a wrong call fails CI."""

from __future__ import annotations

from inboundr import (
    AsyncInboundr,
    Email,
    Inboundr,
    InboundrSignatureError,
    SentEmail,
    read_webhook_headers,
    verify_webhook,
    verify_webhook_delivery,
    verify_webhook_ids,
)

client = Inboundr("inb_x")


def read_and_reply() -> SentEmail:
    page = client.emails.list({"direction": "inbound", "limit": 20})
    first: Email = client.emails.get(page["data"][0]["id"])
    subject: str | None = first["subject"]
    _ = subject
    return client.emails.reply(first["id"], {"text": "Thanks"})


def send() -> str:
    sent = client.emails.send({"from": "a@b.dev", "to": ["c@d.dev"], "subject": "s", "text": "t"})
    return sent["threadId"]


def strict_bodies() -> None:
    client.addresses.create({"domainId": "d", "localPart": "a", "endpointId": "x"})  # type: ignore[typeddict-unknown-key]
    client.domains.update("dom_1", {})  # type: ignore[typeddict-item]
    client.shield_rules.move("sr_1", "left")  # type: ignore[arg-type]
    client.emails.list({"direction": "sideways"})  # type: ignore[arg-type]


def rule_round_trip(rule_id: str) -> None:
    rule = client.shield_rules.get(rule_id)
    client.shield_rules.update(rule_id, {**rule, "enabled": False})


def iterate() -> list[str]:
    return [email["id"] for email in client.emails.list_all({"deliveryStatus": "failed"})]


def webhook(body: bytes, headers: dict[str, str], secret: str) -> str | None:
    try:
        event = verify_webhook(body, headers, secret)
    except InboundrSignatureError as err:
        if err.reason == "missing_body":
            ids = verify_webhook_ids(headers, secret)
            return client.emails.get(ids.email_id)["subject"]
        raise
    _ = read_webhook_headers(headers).delivery_id
    return event["email"]["subject"]


async def use_async() -> list[str]:
    async with AsyncInboundr("inb_x") as aclient:
        page = await aclient.emails.list({"limit": 5})
        ids = [email["id"] async for email in aclient.emails.list_all()]
        return [page["data"][0]["id"], *ids]


def dedupe(body: bytes, headers: dict[str, str], secret: str) -> str:
    delivery = verify_webhook_delivery(body, headers, secret)
    return delivery.delivery_id + ":" + delivery.event["email"]["id"]
