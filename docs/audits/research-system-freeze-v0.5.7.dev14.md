# Research System Freeze Audit — v0.5.7.dev14

## Scope

Covers:
- local research workflow
- paper-only artifacts
- provider discovery
- prompt packets
- simulated provider responses
- response reviews
- dossiers
- check-artifacts
- timeline
- demo workflow
- docs truth
- output safety
- configless local research dispatch
- broker/live boundary isolation

## Result

- **Freeze recommendation from Codex:** Freeze approved — the final Batch 6.11 blocker (absolute path leak in `scripts/demo_research_workflow.sh` stdout) has been resolved.
- **Current version:** 0.5.7.dev14
- **Audit date:** 2026-05-18
- **Blockers found:** None

This audit does not claim production readiness or live-trading readiness.

## Validated Commands

The following commands were run and passed:

- `atlas research providers`
- `atlas research run --symbol SYMBOL`
- `atlas research list`
- `atlas research show RUN_ID`
- `atlas research plan RUN_ID`
- `atlas research verify PLAN_ID`
- `atlas research evaluate PLAN_ID --data PATH`
- `atlas research summary`
- `atlas research check-artifacts`
- `atlas research timeline`
- `atlas research prompt RUN_ID`
- `atlas research simulate-provider PROMPT_PACKET_ID`
- `atlas research review-response PROVIDER_RESPONSE_ID`
- `atlas research dossier RUN_ID`
- `scripts/demo_research_workflow.sh`

**Note:** `atlas research market` remains in CLI help but uses the older provider path and is outside the frozen local artifact-only pipeline. It is not part of this freeze scope.

## Safety Boundaries

The research system maintains the following boundaries:

- No broker submit
- No live broker resolution
- No `OrderRouter.route`
- No approvals
- No pending orders
- No live trading authorization
- No enabled LLM/API/network provider
- Local research commands do not load `.env.atlas` or config secrets

## Artifact Set

The frozen pipeline produces the following artifact types:

- research
- plan
- verification
- evaluation
- prompt packet
- provider response
- response review
- dossier

## Output Safety

The following forbidden fragments are checked in CLI output and artifacts:

- `Authorization`
- `Bearer`
- `APCA`
- `SECRET`
- `TOKEN`
- `PASSWORD`
- `API_KEY`
- `sk-`
- `/Users/`
- `/private/var/`
- `broker.example.com`

All checks passed.

## Demo Integrity

`scripts/demo_research_workflow.sh` validates:

- Full workflow execution (research → plan → verify → evaluate → summary → check-artifacts → timeline → providers → prompt → simulate-provider → review-response → dossier)
- Artifact counts and existence
- Timeline lineage (run_id → plan_id → verification_id → evaluation_id → prompt_packet_id → provider_response_id → response_review_id → dossier_id)
- Provider metadata (deterministic local provider present and default; LLM placeholder disabled)
- No pending orders created
- No unsafe command output
- Full stdout/stderr denylist (no forbidden fragments)
- No git mutation commands

## Validation Commands

Commands run and their results:

| Command | Result |
|---|---|
| `python3.11 -m pytest tests/test_demo_research_workflow_script.py -q` | 43 passed |
| `./scripts/demo_research_workflow.sh` | Exited 0, full output denylist clean |
| `python3.11 -m pytest tests/research/test_research_configless_cli.py -q` | 14 passed |
| `python3.11 -m pytest tests/research -q` | 359 passed |
| `python3.11 -m pytest -q` | 2450 passed |
| `python3.11 -m pip check` | No broken requirements found |
| `./scripts/demo_paper_workflow.sh` | Exited 0 |
| `git diff --check` | Clean |
| `./scripts/release_check.sh` | All release checks passed |
| `python3.11 scripts/check_no_protected_staged.py` | No protected staged files detected |
| `git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk` | No diff |
| Manual full-demo output denylist check | Clean |

## Known Limitations

- Development scope only; not production live-trading readiness.
- Deterministic/local provider only.
- No enabled LLM provider.
- Simulated provider is not a real provider.
- `review-response` is not a real LLM evaluator.
- Dossier is not a trading decision engine.
- `atlas research market` remains legacy and is outside the frozen local pipeline.
- Real broker sandbox/E2E not completed unless separately run.
- Package/tag smoke may require network/build dependencies.

## Follow-ups

Non-blocking findings from the audit:

1. `memory/kill_switch_state.json.lock` is untracked. It is not staged, and the protected-staged guard passes, but `.gitignore` currently only ignores `memory/*.md`, not runtime lock files.
2. `release_check.sh` does not run `./scripts/demo_research_workflow.sh`. The demo passed separately, but research-demo drift remains outside the default aggregate gate.
3. Generic research CLI fallback handlers still serialize `str(exc)` in some paths. The current messages are static codes, but this should be reviewed if new dynamic messages are added.
4. `atlas research market` still exists in help and uses the older provider path, outside the documented frozen chain.

## Recommendation

Research system is frozen for development scope.
