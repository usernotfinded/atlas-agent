# Summary

A codebase hygiene audit was performed to identify and safely remove local, generated, and one-off maintenance files. We also identified a list of unused source modules, which have been deferred for removal until API compatibility can be fully verified.

## Classification taxonomy

| Label | Meaning |
|-------|---------|
| `public_api` | Intentionally kept as a possible public API surface; no internal references currently exist. |
| `cli_or_dynamic` | Referenced dynamically by CLI help text, factory catalogs, resolvers, or provider/broker readiness lists. |
| `test_used` | Imported only by tests; kept for test compatibility or test coverage of a boundary. |
| `compat_shim` | Re-exports or aliases symbols for backward compatibility; no active internal consumers. |
| `fail_closed_stub` | Fail-closed stub or placeholder; explicitly listed in capability inventory or CLI help. |
| `historical` | Cleanup that is already completed; retained in the doc for history only. |

# Completed follow-ups

Earlier batches already completed the safe cleanups:

* Removed one-off maintenance scripts: `bump.py`, `patch_sources.py`
* Removed local runtime and IDE state files: `.atlas_update_state.json`, `.antigravitycli/e5a2f704-d460-434f-829e-9bd713ffb828.json`
* Added strict ignore rules to `.gitignore` to prevent these from being tracked again.
* All 19 deferred source modules were verified importable and kept to preserve public API compatibility.

# Active deferred modules

The following modules are intentionally retained. They have no runtime (`src/`) consumers unless noted otherwise. Each row uses the taxonomy defined above.

| Module | Classification | Evidence | Action |
| ------ | -------------- | -------- | ------ |
| `src/atlas_agent/ai/analyst.py` | `public_api` | No `src/` references. Kept as possible public API. | Retained; importable. |
| `src/atlas_agent/execution/trade_executor.py` | `compat_shim` | Re-exports `OrderRouter`; no `src/` references. | Retained; importable. |
| `src/atlas_agent/market_data/yfinance_provider.py` | `public_api` | No `src/` references; kept as possible public provider API. | Retained; importable. |
| `src/atlas_agent/notifications/slack_stub.py` | `fail_closed_stub` | Listed in `tests/fixtures/product_capability_inventory.json`. | Retained; importable. |
| `src/atlas_agent/notifications/telegram_stub.py` | `fail_closed_stub` | Logically grouped with `slack_stub` as notification stub. | Retained; importable. |
| `src/atlas_agent/reports/adhoc.py` | `public_api` | No `src/` references; CLI tests exercise `generate_adhoc_report`. | Retained; importable. |
| `src/atlas_agent/risk/position_sizing.py` | `public_api` | No `src/` references. Kept as possible public API. | Retained; importable. |
| `src/atlas_agent/safety/policy.py` | `public_api` | No `src/` references. Kept as possible public API. | Retained; importable. |
| `src/atlas_agent/scheduler/cron.py` | `public_api` | Listed in `tests/fixtures/product_capability_inventory.json`; no `src/` runtime references. | Retained; importable. |
| `src/atlas_agent/strategies/base.py` | `public_api` | No `src/` references. Kept as possible public API. | Retained; importable. |
| `src/atlas_agent/strategies/breakout.py` | `public_api` | No `src/` references. Kept as possible public API. | Retained; importable. |
| `src/atlas_agent/strategies/rsi.py` | `public_api` | No `src/` references. Kept as possible public API. | Retained; importable. |
| `src/atlas_agent/tools/contracts.py` | `compat_shim` | Re-exports tool-spec symbols; no `src/` references. | Retained; importable. |
| `src/atlas_agent/tools/runtime.py` | `compat_shim` | Compatibility shim; no `src/` references. | Retained; importable. |
| `src/atlas_agent/setup/inline_select.py` | `public_api` | No `src/` references; tested by `tests/test_setup_ui.py`. | Retained; importable. |
| `src/atlas_agent/risk/validation.py` | `test_used` | Imported only by `tests/test_safety_atlas_blockers.py`. Defines legacy `RiskDecision` distinct from `risk.models.RiskDecision`. | Retained; importable. |
| `src/atlas_agent/ai/signal_parser.py` | `test_used` | Imported only by `tests/test_ai_decision_schema.py`. | Retained; importable. |
| `src/atlas_agent/providers/openrouter.py` | `cli_or_dynamic` | Referenced dynamically by `providers/factory.py`, `providers/catalog.py`, `providers/provider_readiness.py`, and CLI help text. Also tested by `tests/test_runtime_provider_resolution.py`. | Retained; importable. |
| `src/atlas_agent/brokers/ibkr_stub.py` | `cli_or_dynamic` | Referenced by `brokers/resolver.py` `known_brokers` and CLI help text. Also tested by `tests/brokers/test_unsupported_brokers_fail_closed.py`. | Retained; importable. |

# Why no modules are deleted in this batch

This batch only refreshes documentation and tests. No module is deleted because:

* Several modules are plausible public API surfaces (`ai/analyst.py`, `reports/adhoc.py`, `setup/inline_select.py`, strategy modules, etc.).
* `risk/validation.py` and `ai/signal_parser.py` are still imported by existing tests.
* `providers/openrouter.py` and `brokers/ibkr_stub.py` are wired into dynamic CLI/provider/broker catalogs.
* Fail-closed stubs (`slack_stub`, `telegram_stub`) preserve explicit boundary behavior.
* Removing files would require a deprecation path and public-API impact analysis outside the scope of this low-risk docs/test batch.

# Remaining risk

All modules remain importable, preventing `ModuleNotFoundError` crashes. Because they are kept in place, the repository still retains these files. The refreshed taxonomy and tests make the boundary explicit so future maintainers do not accidentally treat deferred modules as unused.

# Recommended next batch

1. Deep architectural review of whether the `strategies` and `ai` modules can be deprecated via semantic versioning.
2. Template source-of-truth simplification (CAND-004).

# Commands used for import/reference search

```bash
for mod in analyst.py trade_executor.py yfinance_provider.py slack_stub.py telegram_stub.py adhoc.py position_sizing.py policy.py cron.py base.py breakout.py rsi.py contracts.py runtime.py inline_select.py validation.py signal_parser.py openrouter.py ibkr_stub.py; do
    grep -rn "import.*${mod%.*}" src tests || true
    grep -rn "from.*import.*${mod%.*}" src tests || true
done
```
