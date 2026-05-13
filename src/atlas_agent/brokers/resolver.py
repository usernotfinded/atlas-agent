from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from atlas_agent.brokers.base import Broker, BrokerProvider
from atlas_agent.brokers.paper import PaperBroker, PaperBrokerAdapter
from atlas_agent.portfolio.state import PortfolioState

if TYPE_CHECKING:
    from atlas_agent.config import AtlasConfig

if TYPE_CHECKING:
    from atlas_agent.config import AtlasConfig


@dataclass(frozen=True)
class BrokerStatus:
    mode: str
    broker_id: str
    configured: bool
    credentials_configured: bool
    can_sync: bool
    can_submit: bool
    code: str
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "mode": self.mode,
            "broker_id": self.broker_id,
            "configured": self.configured,
            "credentials_configured": self.credentials_configured,
            "can_sync": self.can_sync,
            "can_submit": self.can_submit,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class BrokerResolution:
    execution_broker: Broker | None
    sync_provider: BrokerProvider | None
    status: BrokerStatus


class BrokerResolver:
    def __init__(self, config: AtlasConfig | None) -> None:
        self.config = config

    def resolve_status(self, mode: str) -> BrokerStatus:
        if mode == "paper":
            return BrokerStatus(
                mode="paper",
                broker_id="paper",
                configured=True,
                credentials_configured=True,
                can_sync=True,
                can_submit=True,
                code="paper_ready",
                message="paper broker is ready",
            )

        if mode != "live":
            return BrokerStatus(
                mode=mode,
                broker_id="unknown",
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="unknown_mode",
                message=f"unsupported mode: {mode}",
            )

        # Live mode
        if self.config is None:
            return BrokerStatus(
                mode="live",
                broker_id="none",
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_broker_unconfigured",
                message="live broker is not configured",
            )

        broker_id = self.config.live_broker
        if broker_id in {"", "none"}:
            return BrokerStatus(
                mode="live",
                broker_id="none",
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_broker_unconfigured",
                message="live broker is not configured",
            )

        known_brokers = {"alpaca", "binance", "ccxt", "ibkr_stub"}
        if broker_id not in known_brokers:
            return BrokerStatus(
                mode="live",
                broker_id=broker_id,
                configured=False,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_broker_unsupported",
                message="live broker is not supported",
            )

        creds_ok = self._credentials_configured(broker_id)
        if not creds_ok:
            return BrokerStatus(
                mode="live",
                broker_id=broker_id,
                configured=True,
                credentials_configured=False,
                can_sync=False,
                can_submit=False,
                code="live_credentials_missing",
                message="live broker credentials are missing",
            )

        if broker_id == "alpaca":
            return BrokerStatus(
                mode="live",
                broker_id=broker_id,
                configured=True,
                credentials_configured=True,
                can_sync=True,
                can_submit=False,
                code="live_sync_ready",
                message="live Alpaca sync is ready; submit remains disabled",
            )

        return BrokerStatus(
            mode="live",
            broker_id=broker_id,
            configured=True,
            credentials_configured=True,
            can_sync=False,
            can_submit=False,
            code="live_sync_deferred",
            message="live broker is configured but sync and submit are deferred",
        )

    def resolve_sync_provider(self, mode: str) -> BrokerResolution:
        status = self.resolve_status(mode)
        if mode == "paper":
            cash = self.config.starting_cash if self.config else 10000.0
            paper = PaperBroker(state=PortfolioState(cash=cash))
            adapter = PaperBrokerAdapter(broker=paper)
            return BrokerResolution(
                execution_broker=paper,
                sync_provider=adapter,
                status=status,
            )
        if mode == "live" and status.broker_id == "alpaca" and status.can_sync:
            from atlas_agent.brokers.alpaca import AlpacaBrokerAdapter
            return BrokerResolution(
                execution_broker=None,
                sync_provider=AlpacaBrokerAdapter(config=self.config),
                status=status,
            )
        # Live unsupported or unknown: None
        return BrokerResolution(
            execution_broker=None,
            sync_provider=None,
            status=status,
        )

    def resolve_execution_broker(self, mode: str) -> BrokerResolution:
        status = self.resolve_status(mode)
        if mode == "paper":
            cash = self.config.starting_cash if self.config else 10000.0
            paper = PaperBroker(state=PortfolioState(cash=cash))
            adapter = PaperBrokerAdapter(broker=paper)
            return BrokerResolution(
                execution_broker=paper,
                sync_provider=adapter,
                status=status,
            )
        # Live or unknown: always None
        return BrokerResolution(
            execution_broker=None,
            sync_provider=None,
            status=status,
        )

    def _credentials_configured(self, broker_id: str) -> bool:
        if broker_id == "alpaca":
            return bool(os.getenv("ALPACA_API_KEY")) and bool(os.getenv("ALPACA_SECRET_KEY"))
        if broker_id == "binance":
            binance_secret = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")
            return bool(os.getenv("BINANCE_API_KEY")) and bool(binance_secret)
        if broker_id == "ccxt":
            return bool(os.getenv("CCXT_API_KEY")) or bool(os.getenv("EXCHANGE_API_KEY"))
        return False
