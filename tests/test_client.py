"""The REST client against httpx.MockTransport: URLs, headers, bodies, errors."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from inboundr import (
    API_KEY_ENV_VAR,
    AsyncInboundr,
    Inboundr,
    InboundrAPIError,
    InboundrError,
    InboundrRateLimitError,
)

KEY = "inb_test_2mR9Kq4nPj"


def client_with(
    handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
) -> tuple[Inboundr, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(record))
    return Inboundr(KEY, http_client=http, **kwargs), seen


def reply(status: int = 200, body: Any = None, headers: dict[str, str] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status, headers=headers)
        if isinstance(body, (bytes, str)):
            return httpx.Response(status, content=body, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    return handler


# --- construction --------------------------------------------------------------


def test_a_missing_key_raises_up_front(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV_VAR, raising=False)
    with pytest.raises(InboundrError):
        Inboundr()


def test_the_key_falls_back_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV_VAR, KEY)
    seen: list[httpx.Request] = []
    http = httpx.Client(transport=httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(200, json={"data": []}))[1]))
    Inboundr(http_client=http).domains.list()
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"


def test_base_url_trailing_slash_and_user_agent() -> None:
    client, seen = client_with(reply(body={"data": []}), base_url="https://example.test/")
    client.domains.list()
    assert str(seen[0].url) == "https://example.test/api/v1/domains"
    assert seen[0].headers["user-agent"].startswith("inboundr-python/")


# --- requests -------------------------------------------------------------------


def test_query_drops_none_and_encodes_values() -> None:
    client, seen = client_with(reply(body={"data": [], "nextCursor": None}))
    client.emails.list({"to": "a+b@x.dev", "limit": 5, "cursor": None})  # type: ignore[typeddict-item]
    assert seen[0].url.params["to"] == "a+b@x.dev"
    assert seen[0].url.params["limit"] == "5"
    assert "cursor" not in seen[0].url.params


def test_an_address_in_a_path_is_percent_encoded() -> None:
    client, seen = client_with(reply(204))
    client.suppressions.delete("user+tag@example.com")
    assert seen[0].url.raw_path == b"/api/v1/suppressions/user%2Btag%40example.com"


def test_send_posts_json() -> None:
    client, seen = client_with(reply(201, {"id": "em_1", "messageId": None, "threadId": "thr_1"}))
    sent = client.emails.send({"from": "a@x.dev", "to": ["b@x.dev"], "subject": "s", "text": "t"})
    assert seen[0].method == "POST"
    assert seen[0].headers["content-type"] == "application/json"
    assert json.loads(seen[0].content)["from"] == "a@x.dev"
    assert sent["threadId"] == "thr_1"


def test_move_sends_the_direction() -> None:
    client, seen = client_with(reply(body={"order": ["sr_2", "sr_1"]}))
    assert client.shield_rules.move("sr_1", "down")["order"] == ["sr_2", "sr_1"]
    assert seen[0].url.path.endswith("/shield-rules/sr_1/move")
    assert json.loads(seen[0].content) == {"direction": "down"}


def test_a_204_returns_none() -> None:
    client, _ = client_with(reply(204))
    assert client.emails.delete("em_1") is None  # type: ignore[func-returns-value]


def test_download_attachment_returns_bytes() -> None:
    client, seen = client_with(reply(body=b"%PDF", headers={"content-type": "application/pdf"}))
    assert client.emails.download_attachment("em_1", 2) == b"%PDF"
    assert seen[0].url.path.endswith("/emails/em_1/attachments/2")
    assert seen[0].url.params["download"] == "1"


# --- pagination ------------------------------------------------------------------


def test_list_all_follows_next_cursor_and_stops() -> None:
    pages = iter([
        {"data": [{"id": "em_1"}, {"id": "em_2"}], "nextCursor": "c1"},
        {"data": [{"id": "em_3"}], "nextCursor": None},
    ])
    client, seen = client_with(lambda _: httpx.Response(200, json=next(pages)))
    ids = [e["id"] for e in client.emails.list_all({"direction": "inbound", "limit": 2})]
    assert ids == ["em_1", "em_2", "em_3"]
    assert "cursor" not in seen[0].url.params
    assert seen[1].url.params["cursor"] == "c1"
    assert seen[1].url.params["direction"] == "inbound"


def test_breaking_out_of_list_all_stops_fetching() -> None:
    client, seen = client_with(reply(body={"data": [{"id": "a"}, {"id": "b"}], "nextCursor": "more"}))
    for _ in client.emails.list_all():
        break
    assert len(seen) == 1


# --- errors ----------------------------------------------------------------------


def test_a_404_raises_with_status_body_and_request_id() -> None:
    client, _ = client_with(reply(404, {"error": "Email not found"}, {"x-request-id": "req_1"}))
    with pytest.raises(InboundrAPIError) as info:
        client.emails.get("em_x")
    assert (info.value.status, info.value.body, info.value.request_id) == (404, {"error": "Email not found"}, "req_1")
    assert str(info.value) == "Email not found"


def test_a_400_tree_is_kept_in_the_message() -> None:
    tree = {"errors": ['Unrecognized key: "endpointId"']}
    client, _ = client_with(reply(400, {"error": tree}))
    with pytest.raises(InboundrAPIError) as info:
        client.addresses.create({"domainId": "d", "localPart": "a"})
    assert "endpointId" in str(info.value)
    assert info.value.body == {"error": tree}


def test_a_429_carries_retry_after() -> None:
    client, _ = client_with(reply(429, {"error": "slow down"}, {"retry-after": "2"}))
    with pytest.raises(InboundrRateLimitError) as info:
        client.domains.list()
    assert info.value.retry_after_seconds == 2.0


def test_a_429_without_retry_after_is_none() -> None:
    client, _ = client_with(reply(429, {"error": "slow down"}))
    with pytest.raises(InboundrRateLimitError) as info:
        client.domains.list()
    assert info.value.retry_after_seconds is None


def test_a_non_json_error_body_is_kept_as_text() -> None:
    client, _ = client_with(reply(502, "<html>Bad gateway</html>"))
    with pytest.raises(InboundrAPIError) as info:
        client.domains.list()
    assert info.value.body == "<html>Bad gateway</html>"


def test_timeouts_and_transport_failures_raise_inboundr_error() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client, _ = client_with(timeout, timeout=1.5)
    with pytest.raises(InboundrError, match="timed out"):
        client.domains.list()


# --- timeouts --------------------------------------------------------------------


def _timeout_seen(**kwargs: Any) -> Any:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    http = httpx.Client(transport=httpx.MockTransport(handler), timeout=kwargs.pop("client_timeout", 5.0))
    Inboundr(KEY, http_client=http, **kwargs).domains.list()
    return seen[0].extensions["timeout"]


def test_your_own_http_clients_timeout_applies() -> None:
    assert _timeout_seen(client_timeout=120.0)["read"] == 120.0


def test_an_explicit_timeout_overrides_your_client() -> None:
    assert _timeout_seen(client_timeout=120.0, timeout=7.0)["read"] == 7.0


def test_timeout_none_disables_it_only_when_asked() -> None:
    assert _timeout_seen(client_timeout=120.0, timeout=None)["read"] is None


def test_the_default_client_uses_30_seconds() -> None:
    client = Inboundr(KEY)
    assert client._http.timeout.read == 30.0


# --- responses that aren't the API's ------------------------------------------------


def test_a_redirect_names_where_it_points() -> None:
    client, _ = client_with(reply(301, "", {"location": "https://inboundr.net/api/v1/domains"}), base_url="http://inboundr.net")
    with pytest.raises(InboundrAPIError, match="redirect to https://inboundr.net/api/v1/domains"):
        client.domains.list()


def test_a_non_json_success_raises_instead_of_returning_text() -> None:
    client, _ = client_with(reply(200, "<html>Sign in to Wi-Fi</html>", {"content-type": "text/html"}))
    with pytest.raises(InboundrError, match="Expected JSON"):
        list(client.emails.list_all())


def test_list_all_deliveries_pages_through_the_shared_helper() -> None:
    pages = iter([{"data": [{"id": "del_1"}], "nextCursor": "c"}, {"data": [{"id": "del_2"}], "nextCursor": None}])
    client, seen = client_with(lambda _: httpx.Response(200, json=next(pages)))
    assert [d["id"] for d in client.endpoints.list_all_deliveries("ep_1", {"status": "dead"})] == ["del_1", "del_2"]
    assert seen[1].url.params["cursor"] == "c" and seen[1].url.params["status"] == "dead"
    assert seen[0].url.path.endswith("/endpoints/ep_1/deliveries")


def test_list_is_not_exported_over_typing_list() -> None:
    import inboundr

    assert "List" not in inboundr.__all__
    assert "ListResponse" in inboundr.__all__


# --- async -------------------------------------------------------------------------


def test_the_async_client_paginates_and_raises_the_same_way() -> None:
    pages = iter([
        {"data": [{"id": "em_1"}], "nextCursor": "c1"},
        {"data": [{"id": "em_2"}], "nextCursor": None},
    ])

    async def run() -> list[str]:
        http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=next(pages))))
        async with AsyncInboundr(KEY, http_client=http) as client:
            ids = [e["id"] async for e in client.emails.list_all()]
        failing = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(404, json={"error": "nope"})))
        with pytest.raises(InboundrAPIError):
            await AsyncInboundr(KEY, http_client=failing).emails.get("x")
        return ids

    assert asyncio.run(run()) == ["em_1", "em_2"]
