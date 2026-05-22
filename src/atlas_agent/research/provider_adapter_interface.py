"""Provider adapter interface contract — local, configless adapter interface and disabled harness.

This module defines a future adapter interface and a disabled adapter harness.
It does NOT implement any real provider adapter.
It does NOT call any real provider.
It does NOT perform network requests.
It does NOT read API keys.
It does NOT read os.environ.
It does NOT load .env.atlas.
It does NOT import provider SDKs.
It does NOT receive real provider responses.
It does NOT trust provider responses.
It does NOT create trading signals.
It does NOT create approvals or pending orders.
It does NOT authorize live trading.
It does NOT touch brokers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class ProviderAdapterDisabledError(RuntimeError):
    """Raised when the disabled provider adapter is asked to send a request.

    Static safe message only. No raw request, no raw response, no credentials,
    no absolute paths, no provider SDK exception wrapping, no traceback leak.
    """

    def __init__(self, message: str = "provider_adapter_disabled") -> None:
        super().__init__(message)


@dataclass(frozen=True)
class ProviderAdapterCapability:
    """Safe static capability descriptor for a provider adapter."""

    provider_id: str
    adapter_name: str
    adapter_version: str
    adapter_status: str
    supports_text_generation: bool
    supports_streaming: bool
    supports_tool_calls: bool
    supports_network_calls: bool
    supports_credential_loading: bool
    supports_provider_execution: bool
    supports_broker_bridge: bool
    disabled_reason: str


@dataclass(frozen=True)
class ProviderAdapterRequestPreview:
    """Safe representation of a future provider request without body storage."""

    request_preview_id: str
    source_provider_execution_unlock_state_id: str
    source_provider_outbound_payload_preview_id: str
    provider_id: str
    model_id: str
    request_family: str
    payload_hash: str
    payload_body_present: bool
    raw_prompt_present: bool
    credentials_present: bool
    network_required: bool
    provider_call_allowed: bool


@dataclass(frozen=True)
class ProviderAdapterResponsePlaceholder:
    """Safe placeholder for a future response."""

    response_placeholder_id: str
    provider_response_received: bool
    provider_response_trusted: bool
    provider_response_imported: bool
    raw_response_body_present: bool
    response_hash_present: bool
    manual_review_required: bool


@runtime_checkable
class ProviderAdapterProtocol(Protocol):
    """Protocol defining future provider adapter methods."""

    def capabilities(self) -> ProviderAdapterCapability:
        ...

    def build_request_preview(
        self,
        *,
        request_preview_id: str,
        source_provider_execution_unlock_state_id: str,
        source_provider_outbound_payload_preview_id: str,
        provider_id: str,
        model_id: str,
        request_family: str,
        payload_hash: str,
    ) -> ProviderAdapterRequestPreview:
        ...

    def send(self, preview: ProviderAdapterRequestPreview) -> ProviderAdapterResponsePlaceholder:
        ...

    def validate_response_placeholder(self, placeholder: ProviderAdapterResponsePlaceholder) -> bool:
        ...


class DisabledProviderAdapter:
    """Concrete local disabled adapter that never calls providers.

    All execution/network/credential/tool/broker booleans are false.
    send() always raises ProviderAdapterDisabledError.
    """

    def capabilities(self) -> ProviderAdapterCapability:
        return ProviderAdapterCapability(
            provider_id="disabled",
            adapter_name="DisabledProviderAdapter",
            adapter_version="0.0.0",
            adapter_status="disabled",
            supports_text_generation=False,
            supports_streaming=False,
            supports_tool_calls=False,
            supports_network_calls=False,
            supports_credential_loading=False,
            supports_provider_execution=False,
            supports_broker_bridge=False,
            disabled_reason="Provider adapter is disabled. No real provider adapter is implemented.",
        )

    def build_request_preview(
        self,
        *,
        request_preview_id: str,
        source_provider_execution_unlock_state_id: str,
        source_provider_outbound_payload_preview_id: str,
        provider_id: str,
        model_id: str,
        request_family: str,
        payload_hash: str,
    ) -> ProviderAdapterRequestPreview:
        return ProviderAdapterRequestPreview(
            request_preview_id=request_preview_id,
            source_provider_execution_unlock_state_id=source_provider_execution_unlock_state_id,
            source_provider_outbound_payload_preview_id=source_provider_outbound_payload_preview_id,
            provider_id=provider_id,
            model_id=model_id,
            request_family=request_family,
            payload_hash=payload_hash,
            payload_body_present=False,
            raw_prompt_present=False,
            credentials_present=False,
            network_required=False,
            provider_call_allowed=False,
        )

    def send(self, preview: ProviderAdapterRequestPreview) -> ProviderAdapterResponsePlaceholder:
        """Always raises ProviderAdapterDisabledError.

        Never:
        - calls provider
        - calls network
        - imports SDK
        - reads env
        - loads secrets
        - opens files containing credentials
        - returns a successful response
        - marks provider_response_received true
        """
        raise ProviderAdapterDisabledError("provider_adapter_disabled")

    def validate_response_placeholder(self, placeholder: ProviderAdapterResponsePlaceholder) -> bool:
        """Validate that the placeholder only contains safe boolean values."""
        if placeholder.provider_response_received is not False:
            return False
        if placeholder.provider_response_trusted is not False:
            return False
        if placeholder.provider_response_imported is not False:
            return False
        if placeholder.raw_response_body_present is not False:
            return False
        if placeholder.response_hash_present is not False:
            return False
        if placeholder.manual_review_required is not True:
            return False
        return True
