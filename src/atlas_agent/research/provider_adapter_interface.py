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


@dataclass(frozen=True)
class MockProviderAdapterCapability:
    """Safe static capability descriptor for a mock provider adapter.

    All execution/network/credential flags are false.
    Only supports_mock_response is true.
    """

    provider_id: str = "mock"
    adapter_name: str = "mock_provider_adapter"
    adapter_version: str = "0.0.0"
    adapter_status: str = "mock_only_disabled_for_real_execution"
    adapter_family: str = "mock_provider_adapter"
    supports_text_generation: bool = False
    supports_streaming: bool = False
    supports_tool_calls: bool = False
    supports_network_calls: bool = False
    supports_credential_loading: bool = False
    supports_real_provider_execution: bool = False
    supports_mock_response: bool = True
    supports_broker_bridge: bool = False
    mock_only: bool = True
    disabled_for_live_execution: bool = True
    disabled_reason: str = "Mock provider adapter only. No real provider execution."


@dataclass(frozen=True)
class MockProviderRequestPreview:
    """Safe representation of a mock provider request without body storage."""

    mock_request_preview_id: str = ""
    source_provider_adapter_interface_contract_id: str = ""
    source_provider_execution_unlock_state_id: str = ""
    source_provider_outbound_payload_preview_id: str = ""
    provider_id: str = "mock"
    model_id: str = "mock"
    request_family: str = "offline_mock"
    payload_hash: str = ""
    payload_body_present: bool = False
    raw_prompt_present: bool = False
    credentials_present: bool = False
    network_required: bool = False
    provider_call_allowed: bool = False
    mock_generation_allowed: bool = True
    real_provider_request_sent: bool = False


@dataclass(frozen=True)
class MockProviderResponseSimulation:
    """Safe placeholder for a mock provider response simulation.

    No real provider response was received.
    No real provider response is trusted.
    Manual review is always required.
    """

    mock_response_simulation_id: str = ""
    simulation_family: str = "offline_mock_provider_response"
    simulation_status: str = "simulated_response_recorded"
    provider_response_received: bool = False
    provider_response_trusted: bool = False
    provider_response_imported: bool = False
    provider_response_reviewed: bool = False
    raw_response_body_present: bool = False
    raw_response_body_stored: bool = False
    response_hash_present: bool = False
    simulated_response_hash: str = ""
    simulated_response_summary: str = ""
    manual_review_required: bool = True
    trading_signal_generated: bool = False
    approval_created: bool = False
    pending_order_created: bool = False
    broker_touched: bool = False


class MockProviderAdapter:
    """Concrete local mock adapter that never calls real providers.

    simulate_response() returns a deterministic offline mock response.
    send() always raises ProviderAdapterDisabledError (fail-closed).
    """

    def capabilities(self) -> MockProviderAdapterCapability:
        return MockProviderAdapterCapability(
            provider_id="mock",
            adapter_name="mock_provider_adapter",
            adapter_version="0.0.0",
            adapter_status="mock_only_disabled_for_real_execution",
            adapter_family="offline_mock",
            supports_text_generation=False,
            supports_streaming=False,
            supports_tool_calls=False,
            supports_network_calls=False,
            supports_credential_loading=False,
            supports_real_provider_execution=False,
            supports_mock_response=True,
            supports_broker_bridge=False,
            mock_only=True,
            disabled_for_live_execution=True,
            disabled_reason="Mock provider adapter is mock-only. No real provider adapter is implemented.",
        )

    def build_request_preview(
        self,
        *,
        mock_request_preview_id: str,
        source_provider_adapter_interface_contract_id: str,
        source_provider_execution_unlock_state_id: str,
        source_provider_outbound_payload_preview_id: str,
        provider_id: str,
        model_id: str,
        request_family: str,
        payload_hash: str,
    ) -> MockProviderRequestPreview:
        return MockProviderRequestPreview(
            mock_request_preview_id=mock_request_preview_id,
            source_provider_adapter_interface_contract_id=source_provider_adapter_interface_contract_id,
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
            mock_generation_allowed=True,
            real_provider_request_sent=False,
        )

    def simulate_response(
        self,
        preview: MockProviderRequestPreview,
        mock_response_simulation_id: str,
    ) -> MockProviderResponseSimulation:
        """Return a deterministic offline mock response simulation.

        Never calls provider/network.
        Never loads credentials.
        Never returns a trusted response.
        """
        return MockProviderResponseSimulation(
            mock_response_simulation_id=mock_response_simulation_id,
            simulation_family="offline_mock_provider_response",
            simulation_status="simulated_response_recorded",
            provider_response_received=False,
            provider_response_trusted=False,
            provider_response_imported=False,
            provider_response_reviewed=False,
            raw_response_body_present=False,
            raw_response_body_stored=False,
            response_hash_present=True,
            simulated_response_hash=preview.payload_hash,
            simulated_response_summary="offline_mock_response_placeholder_no_provider_call",
            manual_review_required=True,
            trading_signal_generated=False,
            approval_created=False,
            pending_order_created=False,
            broker_touched=False,
        )

    def send(self, preview: MockProviderRequestPreview) -> ProviderAdapterResponsePlaceholder:
        """Always raises ProviderAdapterDisabledError.

        Never calls provider/network.
        Never loads credentials.
        Never returns a successful response.
        """
        raise ProviderAdapterDisabledError("provider_adapter_disabled_mock_adapter_send_not_implemented")


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
