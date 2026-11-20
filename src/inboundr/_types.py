"""Public types.

Everything named after an API shape comes from `_generated/api.py`, which is
generated from openapi/openapi.yaml. The few shapes the spec writes inline
(list wrappers, the thread, a few small responses, query parameters) are
declared here, and tests/test_spec.py checks them against the spec.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from typing_extensions import TypedDict

from ._generated import api as _api

__all__ = [
    "Address", "AttachmentUrl", "CreateAddressParams", "CreateDomainParams", "CreatedAddress",
    "CreateEndpointParams", "CreateForwardDestinationParams", "CreateShieldRuleParams",
    "CreateSuppressionParams", "Delivery", "DeliveryStatus", "DnsRecord", "Domain", "DomainDetail",
    "DomainState", "Email", "EmailAttachment", "EmailDirection", "EmailReceivedEvent", "EmailSummary",
    "Endpoint", "EndpointTestResult", "EndpointType", "EndpointWithSecret", "ForwardDestination",
    "ForwardDestinationRequest", "InboundEmail", "List", "ListDeliveriesParams", "ListEmailsParams",
    "Page", "ReplaceShieldRuleParams", "ReplyParams", "RetryResult", "SendEmailParams", "Sender",
    "SendStatus", "SentEmail", "ShieldAction", "ShieldCondition", "ShieldField", "ShieldOperator",
    "ShieldRule", "ShieldRuleOrder", "Suppression", "SuppressedAddress", "SuppressionReason", "Thread",
    "UpdateAddressParams", "UpdateDomainParams", "UpdatedDomain", "UpdateEndpointParams",
    "WebhookAttachment", "WebhookDeliveryStatus",
]

T = TypeVar("T")

# ------------------------------------------------------------------ shared


class Page(TypedDict, Generic[T]):
    """One page of a paginated list. Pass `nextCursor` back as `cursor`."""

    data: list[T]
    nextCursor: str | None


class List(TypedDict, Generic[T]):
    data: list[T]


# ------------------------------------------------------------------ emails

EmailDirection = _api.EmailDirection
DeliveryStatus = _api.EmailDeliveryStatus
SendStatus = _api.EmailSendStatus
EmailSummary = _api.EmailSummary
Email = _api.Email
EmailAttachment = _api.Attachment
AttachmentUrl = _api.AttachmentUrl
SentEmail = _api.SentEmail
SendEmailParams = _api.SendEmailRequest
ReplyParams = _api.ReplyRequest


class Thread(TypedDict):
    threadId: str
    data: list[EmailSummary]


class RetryResult(TypedDict):
    retried: int


class ListEmailsParams(TypedDict, total=False):
    direction: EmailDirection
    to: str
    threadId: str
    deliveryStatus: DeliveryStatus
    limit: int
    cursor: str


# ------------------------------------------------------------------ domains

DomainState = _api.DomainState
Domain = _api.Domain
DnsRecord = _api.DnsRecord
DomainDetail = _api.DomainWithDns
CreateDomainParams = _api.CreateDomainRequest
UpdateDomainParams = _api.UpdateDomainRequest


class UpdatedDomain(_api.Domain):
    catchAllEndpointIds: list[str]


# ------------------------------------------------------------------ addresses

Address = _api.Address
CreatedAddress = _api.CreatedAddress
CreateAddressParams = _api.CreateAddressRequest
UpdateAddressParams = _api.UpdateAddressRequest

# ------------------------------------------------------------------ endpoints

EndpointType = _api.EndpointType
Endpoint = _api.Endpoint
EndpointWithSecret = _api.CreatedEndpoint
EndpointTestResult = _api.TestDeliveryResult
CreateEndpointParams = _api.CreateEndpointRequest
UpdateEndpointParams = _api.UpdateEndpointRequest
Delivery = _api.Delivery
WebhookDeliveryStatus = _api.DeliveryStatus


class ListDeliveriesParams(TypedDict, total=False):
    status: WebhookDeliveryStatus
    emailId: str
    limit: int
    cursor: str


# ------------------------------------------------------------------ shield rules

ShieldAction = _api.ShieldAction
ShieldField = _api.ShieldField
ShieldOperator = _api.ShieldOperator
ShieldCondition = _api.ShieldCondition
ShieldRule = _api.ShieldRule
ShieldRuleOrder = _api.ShieldRuleOrder
CreateShieldRuleParams = _api.ShieldRuleInput
ReplaceShieldRuleParams = _api.ReplaceShieldRuleRequest

# ------------------------------------------------------------------ senders, suppressions, forwarding

Sender = _api.Sender
SuppressionReason = _api.SuppressionReason
Suppression = _api.Suppression
CreateSuppressionParams = _api.CreateSuppressionRequest
ForwardDestination = _api.ForwardDestination
ForwardDestinationRequest = _api.ForwardDestinationRequest
CreateForwardDestinationParams = _api.CreateForwardDestinationRequest


class SuppressedAddress(TypedDict):
    address: str


# ------------------------------------------------------------------ webhooks

EmailReceivedEvent = _api.EmailReceivedEvent
InboundEmail = _api.Email1
WebhookAttachment = _api.Attachment1

