# Release Checklist

Run this before pushing a public GitHub release.

## Required Validation Commands

- `python3.11 -m pytest -q`
- `python3.11 -m pip check`
- `./scripts/demo_paper_workflow.sh`
- `python3.11 -c "import atlas_agent; print(getattr(atlas_agent, '__version__', 'no __version__'))"`

## Validate Contract Checks

- `atlas validate`
Expectation: human-readable readiness report; command remains read-only.
- `atlas validate --json`
Expectation: one parseable JSON envelope on stdout; no mixed human text; non-strict readiness failures still exit `0`.
- `atlas validate --strict`
Expectation: read-only; exits non-zero (`2`) when readiness checks fail.
- `atlas validate --json --strict`
Expectation: same stable JSON envelope shape as non-strict JSON mode; exits non-zero (`2`) when readiness checks fail.
- Serious config/load/internal failures in any validate mode remain non-zero.

## Release Hygiene Assertions

- Positioning remains broker-neutral supervised workspace, not autonomous trading.
- Demo flow is paper-only and reproducible via `./scripts/demo_paper_workflow.sh`.
- Live trading remains disabled by default unless explicitly enabled by the user.
- No release docs include return guarantees, zero-risk language, autonomous income claims, live-readiness overstatements, or broker-preference marketing language.
- Do not reference a demo GIF as present unless `assets/atlas-demo.gif` actually exists.
- Confirm no private values or credential-like strings are committed in docs or scripts.

## Broker Foundation 3.x Release Assertions

- `can_submit=false` for all live brokers (`BrokerResolver` live status never enables submit).
- `resolve_execution_broker("live")` returns `None` (no live execution broker resolved).
- Live `propose_order` creates no `pending_orders/` files and does not invoke `ApprovalManager`.
- `run_once --mode live` performs broker sync and risk evaluation but does not submit orders, create pending orders, or invoke `ApprovalManager`.
- `run_once --mode live` returns `status="live_analysis_only"` when risk passes; never returns `filled` or `pending_approval`.
- `run_once --mode live` does not instantiate `OrderRouter` or call `OrderRouter.route`.
- `run_once --mode live` does not create files in `pending_orders/`.
- `run_once --mode live` does not call `broker.place_order` on any broker.
- `run_once --mode live` does not call `resolve_execution_broker("live")`.
- `run_once --mode live` requires `enable_live_trading=true`; returns controlled rejection without sync if disabled.
- Synced open orders influence `run_once` live risk evaluation via `PortfolioSnapshot`.
- Alpaca read-only sync is GET-only; `AlpacaBrokerAdapter` implements `BrokerProvider`, not `Broker`, and has no order submission methods.
- Non-Alpaca broker sync (Binance, CCXT, IBKR) remains deferred.
- Docs do not claim production-ready live trading or recommend any specific broker.

## Broker Foundation 4.4 Release Assertions

- `submit-approved-order` without `--dry-run` or `--reconcile` fails controlled (returns "not implemented" error).
- `--dry-run` never mutates pending files.
- `--dry-run` never persists `client_order_id`.
- `--dry-run` never calls broker GET reconciliation (`get_order_by_client_order_id`).
- `--dry-run` never calls `place_order`.
- `--reconcile` never calls `place_order`.
- `--reconcile` never calls `resolve_execution_broker("live")`.
- `--reconcile` never calls `OrderRouter.route`.
- `--reconcile` requires existing `client_order_id` in the pending file.
- `--reconcile` does not compute `client_order_id` when missing (returns `reconcile_not_available`).
- `--reconcile` requires `enable_live_trading=true` before broker query.
- `--reconcile` uses `AlpacaBrokerAdapter.get_order_by_client_order_id` only (read-only GET).
- `BrokerResolver.can_submit` remains `false` for all live brokers.
- `resolve_execution_broker("live")` remains `None`.
- No claims that live trading is ready for unattended deployment or without risk in release docs or README.
