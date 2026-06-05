# Broker Roadmap and Guarded Adapter Status

Atlas Agent is intentionally broker-neutral. The framework ships with a single
safe default execution path (`PaperBroker`) and a small, conservative set of
live adapter statuses. This document describes the current support inventory,
what each adapter can do, and what is intentionally blocked.

> **Safety disclaimer:** Atlas Agent is not financial advice. Live trading is
disabled by default. Live submit is disabled by default. Broker execution is
disabled by default. No profit guarantees are made. Always review your risk
configuration before enabling any live functionality.

## Current Broker Support Inventory

| Broker | Status | Paper | Read-only sync | Live submit | Default enabled | Opt-in required |
|---|---|---|---|---|---|---|
| PaperBroker | `default_paper` | ✅ | ✅ | ❌ | ✅ | No |
| Alpaca | `supported_opt_in` | ❌ | ✅ | ✅* | ❌ | Yes |
| Binance | `partial` | ❌ | ❌ | ❌ | ❌ | Yes |
| CCXT (generic) | `disabled` | ❌ | ❌ | ❌ | ❌ | Yes |
| Interactive Brokers (IBKR) | `placeholder` | ❌ | ❌ | ❌ | ❌ | Yes |

\* Alpaca live submit requires _all_ of the following:

- `broker.provider = "alpaca"`
- `broker.enable_live_trading = true`
- `broker.enable_live_submit = true`
- `trading_mode = "live"`
- Kill switch in `normal` mode
- `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` environment variables
- A valid, non-expired `live_submit_opt_in.jsonl` record matching the current
  broker and config fingerprint
- `order_approval_mode` not set to `disabled_live`
- `risk.allow_leverage = false`

## Status Definitions

- **`default_paper`** — The safe default path. Deterministic local simulation,
  no credentials, no network calls.
- **`supported_opt_in`** — Live functionality exists but is gated behind
  explicit opt-in, credential checks, kill-switch checks, and an opt-in record.
- **`partial`** — Adapter code exists but live submit is deferred pending
  additional safety review. Read-only sync may also be deferred.
- **`disabled`** — The adapter is explicitly disabled. All broker methods raise
  `BrokerConfigurationError`.
- **`placeholder`** — No implementation is provided. Any access raises
  `NotImplementedError`.
- **`unsupported`** — Any broker not listed in the inventory is treated as
  unsupported and blocked at runtime.

## Fail-Closed Behavior

Atlas broker guards are designed to fail closed:

- **Unknown brokers:** `BrokerResolver` returns `live_broker_unsupported` and
  never returns an execution broker.
- **Disabled brokers:** `CCXTBroker` raises `BrokerConfigurationError` on every
  method.
- **Placeholder brokers:** `IBKRStub` raises `NotImplementedError` on any
  attribute access.
- **Partial brokers:** `BinanceBroker` validates credentials but is not
  resolved as a live submit broker by `BrokerResolver`.
- **Missing credentials:** All live brokers raise `BrokerConfigurationError`
  before constructing any transport or exchange object.
- **Missing opt-in:** Even with credentials, live Alpaca submit is rejected
  unless the local opt-in record is valid.

These behaviors are enforced by:

- `BrokerResolver.resolve_execution_broker()` — only resolves an execution
  broker when `status.can_submit` is true.
- `BrokerResolver._resolve_can_submit()` — checks config, kill switch, trading
  mode, approval mode, leverage, credentials, and opt-in record.
- `guard_submit()` and `guard_sync()` in `atlas_agent.brokers.guards` — static
  fail-closed helpers that check the support inventory before any broker call.

## CLI

Read-only broker status commands:

```bash
# List known broker IDs
atlas broker list

# Show support inventory + runtime status (no API calls, no credentials)
atlas broker status
atlas broker status --json
```

Live broker sync requires credentials and is only supported where the inventory
says read-only sync is available:

```bash
# Paper sync is always safe
atlas broker sync --mode paper

# Live sync only works for explicitly supported brokers with credentials
atlas broker sync --mode live
```

## Design Notes

- No broker API calls are made from tests.
- No real credentials are required to run `atlas broker status` or
  `atlas broker list`.
- No new live broker submit path is added without an explicit batch that
  updates this inventory, adds opt-in gates, and adds fail-closed tests.
- The generic CCXT adapter is kept disabled because CCXT's sandbox/testnet
  support varies by exchange and is not uniformly safe for unattended use.
- Binance is partial because the existing adapter requires the `ccxt`
  dependency and additional review of sandbox-vs-live endpoint selection.
- IBKR is a placeholder because the IBKR API requires TWS/Gateway setup,
  paper-account provisioning, and careful review of order types before any
  execution code is introduced.

## References

- `src/atlas_agent/brokers/status.py` — static support inventory
- `src/atlas_agent/brokers/guards.py` — fail-closed guard helpers
- `src/atlas_agent/brokers/resolver.py` — runtime resolution and opt-in logic
- `src/atlas_agent/brokers/alpaca.py` — Alpaca adapter
- `src/atlas_agent/brokers/binance.py` — Binance adapter (partial)
- `src/atlas_agent/brokers/ccxt_adapter.py` — disabled CCXT adapter
- `src/atlas_agent/brokers/ibkr_stub.py` — IBKR placeholder
- `tests/brokers/test_broker_status.py`
- `tests/brokers/test_broker_guards.py`
- `tests/brokers/test_unsupported_brokers_fail_closed.py`
- `tests/cli/test_brokers_cli.py`
