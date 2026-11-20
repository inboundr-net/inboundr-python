"""The client must cover the API exactly as openapi/openapi.yaml describes it.

Every SDK method is called against a mock transport; each request is matched to
a spec operation. An operation no method reaches, or a request the spec doesn't
describe, fails the run, so a new platform route fails this suite after the
next `python scripts/spec.py sync` until the client grows a method for it.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_type_hints

import httpx
import pytest
import yaml

from inboundr import AsyncInboundr, Inboundr
from inboundr import _types as types

ROOT = Path(__file__).resolve().parent.parent
SPEC = yaml.safe_load((ROOT / "openapi" / "openapi.yaml").read_text())
METHODS = ("get", "post", "put", "patch", "delete")
OPERATIONS = [
    {
        "key": f"{m.upper()} {path}",
        "method": m.upper(),
        "pattern": re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"),
        "has_body": "requestBody" in item[m],
    }
    for path, item in SPEC["paths"].items()
    for m in METHODS
    if m in item
]

STUB = {"data": [], "nextCursor": None}


def calls(c: Any) -> list[Callable[[], Any]]:
    rule = {"name": "n", "action": "block", "conditions": [{"field": "subject", "operator": "contains", "value": "x"}]}
    return [
        lambda: c.emails.list(),
        lambda: c.emails.list_all(),
        lambda: c.emails.get("em_1"),
        lambda: c.emails.send({"from": "a@x.dev", "to": ["b@x.dev"], "subject": "s", "text": "t"}),
        lambda: c.emails.reply("em_1", {"text": "t"}),
        lambda: c.emails.delete("em_1"),
        lambda: c.emails.retry("em_1"),
        lambda: c.emails.attachment_url("em_1", 0),
        lambda: c.emails.download_attachment("em_1", 0),
        lambda: c.threads.get("thr_1"),
        lambda: c.domains.list(),
        lambda: c.domains.create({"domain": "x.dev"}),
        lambda: c.domains.get("dom_1"),
        lambda: c.domains.update("dom_1", {"catchAllEndpointIds": []}),
        lambda: c.domains.delete("dom_1"),
        lambda: c.addresses.list(),
        lambda: c.addresses.create({"domainId": "dom_1", "localPart": "a"}),
        lambda: c.addresses.get("addr_1"),
        lambda: c.addresses.update("addr_1", {"active": False}),
        lambda: c.addresses.delete("addr_1"),
        lambda: c.endpoints.list(),
        lambda: c.endpoints.create({"name": "n", "url": "https://x.dev"}),
        lambda: c.endpoints.get("ep_1"),
        lambda: c.endpoints.update("ep_1", {"active": False}),
        lambda: c.endpoints.delete("ep_1"),
        lambda: c.endpoints.test("ep_1"),
        lambda: c.endpoints.deliveries("ep_1"),
        lambda: c.endpoints.list_all_deliveries("ep_1"),
        lambda: c.shield_rules.list(),
        lambda: c.shield_rules.create(rule),
        lambda: c.shield_rules.get("sr_1"),
        lambda: c.shield_rules.update("sr_1", rule),
        lambda: c.shield_rules.delete("sr_1"),
        lambda: c.shield_rules.move("sr_1", "up"),
        lambda: c.shield_rules.reorder(["sr_1"]),
        lambda: c.senders.list(),
        lambda: c.suppressions.list(),
        lambda: c.suppressions.create({"address": "a@x.dev"}),
        lambda: c.suppressions.delete("a@x.dev"),
        lambda: c.forward_destinations.list(),
        lambda: c.forward_destinations.create({"address": "a@x.dev"}),
        lambda: c.forward_destinations.delete("a@x.dev"),
    ]


class Recorder:
    def __init__(self) -> None:
        self.hits: dict[str, httpx.Request] = {}
        self.unmatched: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        op = next((o for o in OPERATIONS if o["method"] == request.method and o["pattern"].match(path)), None)
        if op:
            self.hits[op["key"]] = request
        else:
            self.unmatched.append(f"{request.method} {path}")
        return httpx.Response(200, json=STUB)


def run_sync() -> Recorder:
    rec = Recorder()
    client = Inboundr("inb_x", http_client=httpx.Client(transport=httpx.MockTransport(rec)))
    for call in calls(client):
        result = call()
        if hasattr(result, "__next__"):
            next(result, None)
    return rec


def run_async() -> Recorder:
    rec = Recorder()

    async def go() -> None:
        client = AsyncInboundr("inb_x", http_client=httpx.AsyncClient(transport=httpx.MockTransport(rec)))
        for call in calls(client):
            result = call()
            if hasattr(result, "__anext__"):
                await anext(result, None)
            else:
                await result

    asyncio.run(go())
    return rec


@pytest.mark.parametrize("run", [run_sync, run_async], ids=["sync", "async"])
def test_every_operation_has_a_method_and_every_call_is_in_the_spec(run: Callable[[], Recorder]) -> None:
    rec = run()
    assert rec.unmatched == [], f"requests the spec doesn't describe: {rec.unmatched}"
    missing = [o["key"] for o in OPERATIONS if o["key"] not in rec.hits]
    assert missing == [], f"no SDK method calls: {missing}"
    wrong_body = [o["key"] for o in OPERATIONS if o["has_body"] != bool(rec.hits[o["key"]].content)]
    assert wrong_body == [], f"body sent where the spec has none, or missing: {wrong_body}"


# --- hand-written shapes against the spec --------------------------------------------


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = SPEC["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    if "allOf" in schema:
        merged: dict[str, Any] = {"properties": {}, "required": []}
        for part in schema["allOf"]:
            part = _resolve(part)
            merged["properties"].update(part.get("properties", {}))
            merged["required"] += part.get("required", [])
        return merged
    return schema


def _response(operation_id: str) -> dict[str, Any]:
    for item in SPEC["paths"].values():
        for m in METHODS:
            op = item.get(m)
            if op and op.get("operationId") == operation_id:
                ok = op["responses"].get("200") or op["responses"].get("201")
                return _resolve(ok["content"]["application/json"]["schema"])
    raise KeyError(operation_id)


def _query_names(operation_id: str) -> set[str]:
    for path, item in SPEC["paths"].items():
        for m in METHODS:
            op = item.get(m)
            if op and op.get("operationId") == operation_id:
                params = [*item.get("parameters", []), *op.get("parameters", [])]
                resolved = [SPEC["components"]["parameters"][p["$ref"].rsplit("/", 1)[1]] if "$ref" in p else p for p in params]
                return {p["name"] for p in resolved if p["in"] == "query"}
    raise KeyError(operation_id)


@pytest.mark.parametrize(
    ("typed", "operation_id"),
    [
        (types.Thread, "getThread"),
        (types.RetryResult, "retryEmailDeliveries"),
        (types.UpdatedDomain, "updateDomain"),
        (types.SuppressedAddress, "createSuppression"),
    ],
)
def test_inline_response_types_match_the_spec(typed: Any, operation_id: str) -> None:
    schema = _response(operation_id)
    assert set(get_type_hints(typed)) == set(schema["properties"])
    assert typed.__required_keys__ == set(schema.get("required", []))


@pytest.mark.parametrize(
    ("operation_id", "item"),
    [
        ("listEmails", "EmailSummary"), ("listEndpointDeliveries", "Delivery"),
        ("listDomains", "Domain"), ("listAddresses", "Address"), ("listEndpoints", "Endpoint"),
        ("listShieldRules", "ShieldRule"), ("listSenders", "Sender"),
        ("listSuppressions", "Suppression"), ("listForwardDestinations", "ForwardDestination"),
    ],
)
def test_list_responses_are_page_or_list_of_the_named_schema(operation_id: str, item: str) -> None:
    schema = _response(operation_id)
    data = schema["properties"]["data"]
    assert data["items"]["$ref"].endswith(f"/{item}")
    paginated = "nextCursor" in schema["properties"]
    assert set(schema["properties"]) == ({"data", "nextCursor"} if paginated else {"data"})


@pytest.mark.parametrize(
    ("typed", "operation_id"),
    [(types.ListEmailsParams, "listEmails"), (types.ListDeliveriesParams, "listEndpointDeliveries")],
)
def test_query_param_types_match_the_spec(typed: Any, operation_id: str) -> None:
    assert set(get_type_hints(typed)) == _query_names(operation_id)


# --- generated files are current ---------------------------------------------------------


@pytest.mark.parametrize("script", [["scripts/spec.py", "check"], ["scripts/unasync.py", "--check"]])
def test_generated_files_are_up_to_date(script: list[str]) -> None:
    if script[0] == "scripts/spec.py":
        # The type generator needs Python 3.11+; the package itself supports 3.10.
        pytest.importorskip("datamodel_code_generator")
    result = subprocess.run([sys.executable, *script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
