# Post Research System Audit

## Scope

This audit covers the state of the Atlas Agent research workflow system after the Batch 5.3x development batches and the associated Codex audit.

Areas reviewed:

- Release / version hygiene
- Paper-only research workflow
- Research artifact schema versioning
- Artifact health checks
- Timeline / lineage inspection
- Demo workflow integrity
- Docs-truth constraints
- Output safety (CLI error sanitization)
- Live-submit / broker boundary isolation
- Workspace hygiene

## Audit Result

- **Blocking issues:** none found
- **Final recommendation:** PUSH OK
- **Audit date:** 2026-05-16
- **Current version:** 0.5.7.dev8

This audit does not claim production readiness or live-trading readiness.

## Validation Commands

The following commands were run and passed:

- `python3.11 scripts/check_version_consistency.py`
- `python3.11 scripts/check_forbidden_claims.py`
- `python3.11 -m pytest tests/research -q`
- `python3.11 -m pytest tests/test_demo_research_workflow_script.py -q`
- `python3.11 -m pytest tests/test_research_workflow_docs.py tests/test_research_workflow_reference_docs.py -q`
- `python3.11 -m pytest -q`
- `python3.11 -m pip check`
- `./scripts/demo_paper_workflow.sh`
- `./scripts/demo_research_workflow.sh`
- `git diff --check`
- `./scripts/release_check.sh`
- `python3.11 scripts/check_no_protected_staged.py`

## Research Workflow Status

The following commands are present and covered by tests:

- `atlas research run --symbol SYMBOL`
- `atlas research list`
- `atlas research show RUN_ID`
- `atlas research plan RUN_ID`
- `atlas research verify PLAN_ID`
- `atlas research evaluate PLAN_ID --data PATH`
- `atlas research summary`
- `atlas research check-artifacts`
- `atlas research timeline`
- `./scripts/demo_research_workflow.sh`

Properties:

- Paper-only
- Analysis-only
- Local artifacts (no remote persistence)
- Deterministic / local provider only
- No broker credentials required

## Safety Boundaries Verified

The audit verified that the research workflow does **not**:

- call `place_order`
- call `resolve_execution_broker("live")`
- call `OrderRouter.route`
- create approvals
- create pending orders
- mutate pending orders
- authorize live trading
- require broker credentials

Additional boundaries:

- Live submit remains disabled by default
- Safe quote gate remains execution-time only, not part of `can_submit`
- Reconcile remains read-only

## Artifact Safety

- New research artifacts include `schema_version`
- Paper plan artifacts include `schema_version`
- Verification artifacts include `schema_version`
- Evaluation artifacts include `schema_version`
- Legacy artifacts without `schema_version` load where safe
- Unsupported future schema versions fail closed
- Malformed JSON is handled safely
- Duplicate IDs are detected where expected
- Artifact paths are workspace-relative in output
- Symlink / path containment prevents outside reads
- `check-artifacts` is read-only and does not migrate, rewrite, repair, delete, or modify artifacts

## Timeline / Lineage

- `atlas research timeline` is read-only
- Timeline reconstructs: research -> plan -> verification / evaluation
- `demo_research_workflow.sh` validates: `run_id` -> `plan_id` -> `verification_id` -> `evaluation_id`
- Timeline / demo fail on broken or missing lineage where required by the demo

## Output Safety

Manual leak checks passed for:

- Invalid `--symbol` values containing `/Users/natan/secret`
- Unsupported `--provider` values containing `sk-LEAKEDSECRET123456`

Output did **not** leak:

- `/Users/`
- `/private/var/`
- `natan`
- `secret`
- `LEAKEDSECRET`
- `SECRET`
- `TOKEN`
- `PASSWORD`
- `Authorization`
- `Bearer`
- `APCA`
- `sk-`

CLI errors use static safe messages for invalid symbol and unsupported provider. Raw exception output was not observed in the audited blocker paths.

## Docs Truth

Docs were checked for avoiding claims of:

- investment advisory language
- signal-based trade recommendations
- directional buy/sell suggestions
- projected earnings claims
- promises of assured performance
- assertions that trading carries no downside
- claims that live execution is without hazard
- assertions of readiness for real-market deployment
- unsupervised algorithmic execution claims
- research output being treated as permission to execute live orders

## Non-Blocking Findings

1. `memory/kill_switch_state.json.lock` is untracked. It is not staged, and the protected-staged guard passes, but `.gitignore` currently only ignores `memory/*.md`, not runtime lock files.
2. `release_check.sh` does not run `./scripts/demo_research_workflow.sh`. The demo passed separately, but research-demo drift remains outside the default aggregate gate.

These are not blockers.

## Missing Tests / Follow-ups

- Add negative tests for generic `ResearchSessionError` fallback paths with unsafe exception text.
- Optionally broaden unsupported-provider leak assertions for `plan`, `verify`, and `evaluate` to include all forbidden fragments.

## Suspicious Areas for Manual Follow-Up

- Generic research CLI fallback handlers still serialize `str(exc)` in some paths. The current messages are static codes, but this should be reviewed if new dynamic messages are added:
  - `src/atlas_agent/cli.py` around research handlers
- `atlas research market` still exists in help and uses the older provider path, outside the documented Batch 5.40 chain.
- `release_check.sh` does not include `demo_research_workflow.sh`.

These are not blockers.

## Known Limitations

- Development-stage system
- Deterministic / local research provider only
- No LLM research provider enabled
- No real broker E2E / sandbox verification unless separately run
- Package / tag smoke scripts may require network / build dependencies
- Research evaluation checks local data availability and objective metrics, not profitability
- Research workflow is not financial advice and not live-trading authorization

## Recommendation

Current research system audit passes for development scope.

- Safe to proceed with next development batch.
- Do not treat this as production live-trading readiness.
