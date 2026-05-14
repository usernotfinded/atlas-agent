from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.cli import run_once
from atlas_agent.config import AtlasConfig
from atlas_agent.execution.order import OrderResult


def _make_config(
    tmp_path: Path,
    *,
    enable_live_trading: bool = True,
    max_position_notional: float = 1000.0,
    max_order_notional: float = 500.0,
) -> AtlasConfig:
    config = AtlasConfig(
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        pending_orders_dir=tmp_path / "pending_orders",
        reports_dir=tmp_path / "reports",
        events_dir=tmp_path / "events",
        workspace_root=tmp_path,
        broker={"enable_live_trading": enable_live_trading},
        risk={
            "max_position_notional": max_position_notional,
            "max_order_notional": max_order_notional,
        },
        backtest={"data_path": tmp_path / "data" / "ohlcv.csv"},
    )
    config.ensure_dirs()
    return config


def _write_sample_data(data_path: Path, symbol: str = "DEMO-SYMBOL") -> None:
    data_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["date,symbol,open,high,low,close,volume"]
    base_price = 100.0
    for i in range(6):
        p = base_price + i
        lines.append(f"2024-01-0{i+1},{symbol},{p-1},{p+1},{p-1},{p},1000")
    data_path.write_text("\n".join(lines) + "\n")


def test_run_once_live_disabled_returns_rejected(tmp_path: Path) -> None:
    config = _make_config(tmp_path, enable_live_trading=False)
    _write_sample_data(config.data_path)

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "rejected"
    assert "live_trading_disabled" in result.reasons
    assert "not enabled" in result.message.lower()


@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
def test_run_once_live_sync_success_returns_analysis_only(
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot

    config = _make_config(tmp_path)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="success",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    snapshot = PortfolioSnapshot(cash=10000.0, equity=10000.0, total_exposure=0.0)
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = ([], None)

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "live_analysis_only"
    assert result.accepted is False
    assert result.filled is False
    assert "live_submit_deferred" in result.reasons
    mock_validate.assert_called_once()
    mock_sync_service.sync.assert_called_once()


@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
def test_run_once_live_sync_critical_failure_returns_rejected(
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult

    config = _make_config(tmp_path)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="failed",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = (
        [],
        {
            "status": "error",
            "errors": ["live broker sync failed: sync_account_state"],
            "diagnostics": {
                "broker_status": {},
                "sync_status": "failed",
                "failed_operations": ["sync_account_state"],
            },
        },
    )

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "rejected"
    assert "sync_account_state" in result.reasons
    mock_validate.assert_called_once()



@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
def test_run_once_live_risk_rejection_with_real_portfolio(
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition

    config = _make_config(tmp_path, max_position_notional=500.0, max_order_notional=500.0)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="success",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    # Existing position of 10 shares at avg price 100 = 1000 notional
    # This exceeds max_position_notional=500, so any new buy should be rejected
    snapshot = PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=1000.0,
        positions=[
            RiskPosition(
                symbol="DEMO-SYMBOL",
                quantity=10.0,
                average_price=100.0,
                market_price=100.0,
                notional=1000.0,
                side="long",
            )
        ],
    )
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = ([], None)

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "rejected"
    assert "risk manager rejected order" in result.message.lower()



@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
def test_run_once_live_open_orders_affect_risk(
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition, PendingOrder

    config = _make_config(tmp_path, max_position_notional=800.0, max_order_notional=500.0)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="success",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    # Existing position: 3 shares at 100 = 300 notional
    # Pending open order: buy 3 more shares = 300 additional
    # Proposed order is ~500 notional (max_order_notional / latest_close = 500/105 ~ 4.76 shares)
    # Total projected with pending = 300 + 300 + 500 = 1100 > 800
    snapshot = PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=300.0,
        positions=[
            RiskPosition(
                symbol="DEMO-SYMBOL",
                quantity=3.0,
                average_price=100.0,
                market_price=105.0,
                notional=315.0,
                side="long",
            )
        ],
        open_orders=[
            PendingOrder(
                order_id="pending-1",
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=3.0,
                status="open",
                filled_quantity=0.0,
            )
        ],
    )
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = ([], None)

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "rejected"
    assert "risk manager rejected order" in result.message.lower()



@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
def test_run_once_live_sync_warning_surfaces_in_reasons(
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot

    config = _make_config(tmp_path)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="partial",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    snapshot = PortfolioSnapshot(cash=10000.0, equity=10000.0, total_exposure=0.0)
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = (
        [{"operation": "sync_balances", "code": "broker_operation_failed", "broker": "alpaca"}],
        None,
    )

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "live_analysis_only"
    assert "live_submit_deferred" in result.reasons
    assert "sync_balances_warning" in result.reasons
    assert "sync_balances" in result.message



@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
@patch("atlas_agent.cli._broker_for_mode")
@patch("atlas_agent.cli.OrderRouter")
@patch("atlas_agent.cli.ApprovalManager")
def test_run_once_live_analysis_path_never_reaches_execution_artifacts(
    mock_approval_manager_cls,
    mock_order_router_cls,
    mock_broker_for_mode,
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    """Live analysis-only path must not touch any execution or approval artifacts."""
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot

    config = _make_config(tmp_path)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )
    # Ensure resolve_execution_broker is trackable on the mock class
    mock_resolver_cls.return_value.resolve_execution_broker = MagicMock()

    sync_result = BrokerSyncResult(
        status="success",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    snapshot = PortfolioSnapshot(cash=10000.0, equity=10000.0, total_exposure=0.0)
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = ([], None)

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "live_analysis_only"

    # Execution/approval artifacts must never be reached
    mock_broker_for_mode.assert_not_called()
    mock_order_router_cls.assert_not_called()
    mock_approval_manager_cls.assert_not_called()
    mock_resolver_cls.return_value.resolve_execution_broker.assert_not_called()

    # No pending order files should exist
    pending_files = list(config.pending_orders_dir.iterdir())
    assert pending_files == []



@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
@patch("atlas_agent.risk.manager.RiskManager")
def test_run_once_live_evaluate_order_receives_snapshot_with_open_orders(
    mock_risk_manager_cls,
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    """RiskManager.evaluate_order must receive a PortfolioSnapshot containing synced open_orders."""
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot, RiskPosition, PendingOrder, RiskDecision

    config = _make_config(tmp_path)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="success",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    snapshot = PortfolioSnapshot(
        cash=10000.0,
        equity=10000.0,
        total_exposure=0.0,
        positions=[
            RiskPosition(
                symbol="DEMO-SYMBOL",
                quantity=1.0,
                average_price=100.0,
                market_price=100.0,
                notional=100.0,
                side="long",
            )
        ],
        open_orders=[
            PendingOrder(
                order_id="open-1",
                symbol="DEMO-SYMBOL",
                side="buy",
                quantity=2.0,
                status="open",
                filled_quantity=0.0,
            )
        ],
    )
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = ([], None)

    # Risk decision passes
    mock_risk_manager_cls.return_value.evaluate_order.return_value = RiskDecision(
        allowed=True,
        status="allowed",
        reason="test pass",
        violations=[],
        classification="opens_new_position",
    )

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    assert result.status == "live_analysis_only"

    # Verify evaluate_order was called with a PortfolioSnapshot that has open_orders
    mock_risk_manager_cls.return_value.evaluate_order.assert_called_once()
    call_args = mock_risk_manager_cls.return_value.evaluate_order.call_args
    passed_snapshot = call_args[0][1]
    assert isinstance(passed_snapshot, PortfolioSnapshot)
    assert len(passed_snapshot.open_orders) == 1
    assert passed_snapshot.open_orders[0].order_id == "open-1"
    assert passed_snapshot.open_orders[0].symbol == "DEMO-SYMBOL"
    assert call_args.kwargs.get("mode") == "live"



def test_run_once_paper_path_unchanged(tmp_path: Path) -> None:
    """Paper mode must continue to use synthetic PortfolioState and execute through OrderRouter."""
    config = _make_config(tmp_path, enable_live_trading=False)
    _write_sample_data(config.data_path)

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="paper", config=config, symbol="DEMO-SYMBOL")

    assert isinstance(result, OrderResult)
    # Paper mode with sample data and default config should fill
    assert result.status == "filled"
    assert result.accepted is True
    assert result.filled is True


@patch("atlas_agent.brokers.resolver.BrokerResolver")
@patch("atlas_agent.brokers.sync.BrokerSyncService")
@patch("atlas_agent.brokers.live_sync_validation.validate_live_sync")
def test_run_once_live_no_broker_place_order_called(
    mock_validate,
    mock_sync_service_cls,
    mock_resolver_cls,
    tmp_path: Path,
) -> None:
    """No broker.place_order must be invoked in live analysis-only path."""
    from atlas_agent.brokers.models import BrokerAccountState, BrokerSyncResult
    from atlas_agent.risk.models import PortfolioSnapshot

    config = _make_config(tmp_path)
    _write_sample_data(config.data_path)

    mock_resolver_cls.return_value.resolve_status.return_value = MagicMock(
        can_sync=True,
        broker_id="alpaca",
        mode="live",
        configured=True,
        credentials_configured=True,
        can_submit=False,
        code="live_sync_ready",
        message="live sync ready",
    )
    mock_resolver_cls.return_value.resolve_sync_provider.return_value = MagicMock(
        sync_provider=MagicMock(),
        status=MagicMock(),
    )

    sync_result = BrokerSyncResult(
        status="success",
        account=BrokerAccountState(account_id="acc-1", cash=10000.0, equity=10000.0),
        diagnostics={"broker_errors": []},
    )
    mock_sync_service = MagicMock()
    mock_sync_service.sync.return_value = sync_result
    snapshot = PortfolioSnapshot(cash=10000.0, equity=10000.0, total_exposure=0.0)
    mock_sync_service.get_portfolio_snapshot.return_value = snapshot
    mock_sync_service_cls.return_value = mock_sync_service

    mock_validate.return_value = ([], None)

    # Patch the underlying broker provider to ensure place_order cannot be called
    mock_sync_provider = mock_resolver_cls.return_value.resolve_sync_provider.return_value.sync_provider
    mock_sync_provider.place_order = MagicMock()

    with patch("atlas_agent.ai.discipline.require_user_discipline"):
        result = run_once(mode="live", config=config, symbol="DEMO-SYMBOL")

    assert result.status == "live_analysis_only"
    mock_sync_provider.place_order.assert_not_called()
