"""The async client. `_client.py` is generated from this file by
scripts/unasync.py; edit this one and regenerate."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal, cast

import httpx

from . import _base
from ._types import (
    Address,
    AttachmentUrl,
    CreateAddressParams,
    CreatedAddress,
    CreateDomainParams,
    CreateEndpointParams,
    CreateForwardDestinationParams,
    CreateShieldRuleParams,
    CreateSuppressionParams,
    Delivery,
    Domain,
    DomainDetail,
    Email,
    EmailSummary,
    Endpoint,
    EndpointTestResult,
    EndpointWithSecret,
    ForwardDestination,
    ForwardDestinationRequest,
    List,
    ListDeliveriesParams,
    ListEmailsParams,
    Page,
    ReplaceShieldRuleParams,
    ReplyParams,
    RetryResult,
    Sender,
    SendEmailParams,
    SentEmail,
    ShieldRule,
    ShieldRuleOrder,
    SuppressedAddress,
    Suppression,
    Thread,
    UpdateAddressParams,
    UpdatedDomain,
    UpdateDomainParams,
    UpdateEndpointParams,
)

__all__ = ["AsyncInboundr"]

_seg = _base.segment


class AsyncInboundr:
    """Client for the Inboundr API.

    ::

        client = AsyncInboundr()               # reads INBOUNDR_API_KEY
        client = AsyncInboundr("inb_...")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _base.DEFAULT_BASE_URL,
        timeout: float | None = _base.DEFAULT_TIMEOUT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        key = _base.resolve_api_key(api_key)
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)
        self._url = _base.base_api_url(self.base_url)
        self._headers = _base.default_headers(key)

        self.emails = AsyncEmails(self)
        self.threads = AsyncThreads(self)
        self.domains = AsyncDomains(self)
        self.addresses = AsyncAddresses(self)
        self.endpoints = AsyncEndpoints(self)
        self.shield_rules = AsyncShieldRules(self)
        self.senders = AsyncSenders(self)
        self.suppressions = AsyncSuppressions(self)
        self.forward_destinations = AsyncForwardDestinations(self)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        query: Any = None,
        body: Any = None,
        raw: bool = False,
    ) -> Any:
        try:
            response = await self._http.request(
                method,
                self._url + path,
                params=_base.clean_query(query),
                json=body,
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise _base.transport_error(method, path, exc, self._timeout) from exc
        return _base.handle_response(response, raw=raw)

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncInboundr:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class _AsyncResource:
    def __init__(self, client: AsyncInboundr) -> None:
        self._client = client


class AsyncEmails(_AsyncResource):
    async def list(self, params: ListEmailsParams | None = None) -> Page[EmailSummary]:
        """One page of emails, newest first. Bodies are omitted; use `get`."""
        return cast(Page[EmailSummary], await self._client._request("GET", "/emails", query=params))

    async def list_all(self, params: ListEmailsParams | None = None) -> AsyncIterator[EmailSummary]:
        """Every matching email, newest first, fetching pages as you iterate."""
        query: dict[str, Any] = dict(params or {})
        while True:
            page = await self.list(cast(ListEmailsParams, query))
            for item in page["data"]:
                yield item
            if not page["nextCursor"]:
                return
            query["cursor"] = page["nextCursor"]

    async def get(self, id: str) -> Email:
        return cast(Email, await self._client._request("GET", f"/emails/{_seg(id)}"))

    async def send(self, params: SendEmailParams) -> SentEmail:
        """Send an email. Not idempotent: retrying after a timeout can send it twice."""
        return cast(SentEmail, await self._client._request("POST", "/emails", body=params))

    async def reply(self, id: str, params: ReplyParams) -> SentEmail:
        """Reply to a received email. Recipients and threading come from the stored message."""
        return cast(SentEmail, await self._client._request("POST", f"/emails/{_seg(id)}/reply", body=params))

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/emails/{_seg(id)}")

    async def retry(self, id: str) -> RetryResult:
        """Retry this email's failed webhook deliveries."""
        return cast(RetryResult, await self._client._request("POST", f"/emails/{_seg(id)}/retry"))

    async def attachment_url(self, email_id: str, index: int) -> AttachmentUrl:
        """A signed download URL for one attachment, valid for 15 minutes."""
        return cast(
            AttachmentUrl,
            await self._client._request("GET", f"/emails/{_seg(email_id)}/attachments/{int(index)}"),
        )

    async def download_attachment(self, email_id: str, index: int) -> bytes:
        """The attachment's bytes, streamed through the API."""
        return cast(
            bytes,
            await self._client._request(
                "GET",
                f"/emails/{_seg(email_id)}/attachments/{int(index)}",
                query={"download": "1"},
                raw=True,
            ),
        )


class AsyncThreads(_AsyncResource):
    async def get(self, id: str) -> Thread:
        """Every message in a thread, oldest first."""
        return cast(Thread, await self._client._request("GET", f"/threads/{_seg(id)}"))


class AsyncDomains(_AsyncResource):
    async def list(self) -> List[Domain]:
        return cast(List[Domain], await self._client._request("GET", "/domains"))

    async def create(self, params: CreateDomainParams) -> DomainDetail:
        """Register a domain. Publish the returned `dnsRecords`, then poll `get`."""
        return cast(DomainDetail, await self._client._request("POST", "/domains", body=params))

    async def get(self, id: str) -> DomainDetail:
        """Fetch a domain and re-check its verification."""
        return cast(DomainDetail, await self._client._request("GET", f"/domains/{_seg(id)}"))

    async def update(self, id: str, params: UpdateDomainParams) -> UpdatedDomain:
        """Set the catch-all endpoints. An empty list turns the catch-all off."""
        return cast(UpdatedDomain, await self._client._request("PATCH", f"/domains/{_seg(id)}", body=params))

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/domains/{_seg(id)}")


class AsyncAddresses(_AsyncResource):
    async def list(self) -> List[Address]:
        return cast(List[Address], await self._client._request("GET", "/addresses"))

    async def create(self, params: CreateAddressParams) -> CreatedAddress:
        """With no `endpointIds` the address is store-only."""
        return cast(CreatedAddress, await self._client._request("POST", "/addresses", body=params))

    async def get(self, id: str) -> Address:
        return cast(Address, await self._client._request("GET", f"/addresses/{_seg(id)}"))

    async def update(self, id: str, params: UpdateAddressParams) -> Address:
        """`endpointIds` replaces the whole set; an empty list makes the address store-only."""
        return cast(Address, await self._client._request("PATCH", f"/addresses/{_seg(id)}", body=params))

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/addresses/{_seg(id)}")


class AsyncEndpoints(_AsyncResource):
    async def list(self) -> List[Endpoint]:
        return cast(List[Endpoint], await self._client._request("GET", "/endpoints"))

    async def create(self, params: CreateEndpointParams) -> EndpointWithSecret:
        """Create an endpoint. The response is the only time `secret` is returned."""
        return cast(EndpointWithSecret, await self._client._request("POST", "/endpoints", body=params))

    async def get(self, id: str) -> Endpoint:
        return cast(Endpoint, await self._client._request("GET", f"/endpoints/{_seg(id)}"))

    async def update(self, id: str, params: UpdateEndpointParams) -> Endpoint:
        """A partial update: send only the fields you are changing."""
        return cast(Endpoint, await self._client._request("PATCH", f"/endpoints/{_seg(id)}", body=params))

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/endpoints/{_seg(id)}")

    async def test(self, id: str) -> EndpointTestResult:
        """Send a signed sample delivery and report the outcome."""
        return cast(EndpointTestResult, await self._client._request("POST", f"/endpoints/{_seg(id)}/test"))

    async def deliveries(self, id: str, params: ListDeliveriesParams | None = None) -> Page[Delivery]:
        """One page of this endpoint's deliveries, newest first."""
        return cast(
            Page[Delivery],
            await self._client._request("GET", f"/endpoints/{_seg(id)}/deliveries", query=params),
        )

    async def list_all_deliveries(
        self, id: str, params: ListDeliveriesParams | None = None
    ) -> AsyncIterator[Delivery]:
        """Every matching delivery, newest first, fetching pages as you iterate."""
        query: dict[str, Any] = dict(params or {})
        while True:
            page = await self.deliveries(id, cast(ListDeliveriesParams, query))
            for item in page["data"]:
                yield item
            if not page["nextCursor"]:
                return
            query["cursor"] = page["nextCursor"]


class AsyncShieldRules(_AsyncResource):
    async def list(self) -> List[ShieldRule]:
        """Rules in evaluation order. The first match wins."""
        return cast(List[ShieldRule], await self._client._request("GET", "/shield-rules"))

    async def create(self, params: CreateShieldRuleParams) -> ShieldRule:
        """Create a rule. It goes last in the order."""
        return cast(ShieldRule, await self._client._request("POST", "/shield-rules", body=params))

    async def get(self, id: str) -> ShieldRule:
        return cast(ShieldRule, await self._client._request("GET", f"/shield-rules/{_seg(id)}"))

    async def update(self, id: str, params: ReplaceShieldRuleParams | ShieldRule) -> ShieldRule:
        """Replace a rule. A rule from `get` can be passed back with changes;
        the API ignores its read-only fields (id, priority, scope, createdAt)::

            rule = client.shield_rules.get(rule_id)
            client.shield_rules.update(rule_id, {**rule, "enabled": False})
        """
        return cast(ShieldRule, await self._client._request("PUT", f"/shield-rules/{_seg(id)}", body=params))

    async def delete(self, id: str) -> None:
        await self._client._request("DELETE", f"/shield-rules/{_seg(id)}")

    async def move(self, id: str, direction: Literal["up", "down"]) -> ShieldRuleOrder:
        """Swap the rule with its neighbour. Returns the new order."""
        return cast(
            ShieldRuleOrder,
            await self._client._request("POST", f"/shield-rules/{_seg(id)}/move", body={"direction": direction}),
        )

    async def reorder(self, order: Sequence[str]) -> ShieldRuleOrder:
        """Set the whole order. `order` must name every rule exactly once."""
        return cast(ShieldRuleOrder, await self._client._request("PUT", "/shield-rules", body={"order": [*order]}))


class AsyncSenders(_AsyncResource):
    async def list(self) -> List[Sender]:
        """Senders connected in the console."""
        return cast(List[Sender], await self._client._request("GET", "/senders"))


class AsyncSuppressions(_AsyncResource):
    async def list(self) -> List[Suppression]:
        return cast(List[Suppression], await self._client._request("GET", "/suppressions"))

    async def create(self, params: CreateSuppressionParams) -> SuppressedAddress:
        return cast(SuppressedAddress, await self._client._request("POST", "/suppressions", body=params))

    async def delete(self, address: str) -> None:
        await self._client._request("DELETE", f"/suppressions/{_seg(address)}")


class AsyncForwardDestinations(_AsyncResource):
    async def list(self) -> List[ForwardDestination]:
        return cast(List[ForwardDestination], await self._client._request("GET", "/forward-destinations"))

    async def create(self, params: CreateForwardDestinationParams) -> ForwardDestinationRequest:
        """Ask an address to confirm it will accept forwarded mail."""
        return cast(
            ForwardDestinationRequest,
            await self._client._request("POST", "/forward-destinations", body=params),
        )

    async def delete(self, address: str) -> None:
        await self._client._request("DELETE", f"/forward-destinations/{_seg(address)}")
