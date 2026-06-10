# Summary

A codebase hygiene audit was performed to identify and safely remove local, generated, and one-off maintenance files. We also identified a list of unused source modules, which have been deferred for removal until API compatibility can be fully verified.

# Safe cleanup completed in this batch

* Removed one-off maintenance scripts: `bump.py`, `patch_sources.py`
* Removed local runtime and IDE state files: `.atlas_update_state.json`, `.antigravitycli/e5a2f704-d460-434f-829e-9bd713ffb828.json`
* Added strict ignore rules to `.gitignore` to prevent these from being tracked again.

# Deferred candidates

The following modules were flagged as unused or containing duplicate functionality, but were deferred from removal in this batch:

* `ai/analyst.py` (candidate)
* `execution/trade_executor.py` (candidate)
* `market_data/yfinance_provider.py` (candidate)
* `notifications/slack_stub.py` (candidate)
* `notifications/telegram_stub.py` (candidate)
* `reports/adhoc.py` (candidate)
* `risk/position_sizing.py` (candidate)
* `safety/policy.py` (candidate)
* `scheduler/cron.py` (candidate)
* `strategies/base.py` (candidate)
* `strategies/breakout.py` (candidate)
* `strategies/rsi.py` (candidate)
* `tools/contracts.py` (candidate)
* `tools/runtime.py` (candidate)
* `setup/inline_select.py` (candidate)

Duplicate/merge candidates:
* `risk/validation.py`
* `ai/signal_parser.py`
* `providers/openrouter.py`
* `ibkr_stub.py`

# Why source modules were not removed now

These files were not removed in this batch because they require API compatibility verification. While static grep searches indicate they may be dead code, there is not yet strong proof they are not used as a public API or loaded dynamically (e.g., via `importlib`). Any removal needs to be provably safe and properly tested.

# Recommended next batch

1. Verify if the above modules are part of the public API or dynamically loaded by user configurations.
2. If safe, remove the dead code and run full integration suites to guarantee no runtime behavior changes.
3. Consolidate the duplicate/merge candidates.
4. Refactor `tests/test_demo_research_workflow_script.py` by abstracting the mock script generation.

# Commands used for import/reference search

```bash
for mod in analyst.py trade_executor.py yfinance_provider.py slack_stub.py telegram_stub.py adhoc.py position_sizing.py policy.py cron.py base.py breakout.py rsi.py contracts.py runtime.py inline_select.py validation.py signal_parser.py openrouter.py ibkr_stub.py; do
    grep -rn "import.*${mod%.*}" src tests || true
    grep -rn "from.*import.*${mod%.*}" src tests || true
done
```
