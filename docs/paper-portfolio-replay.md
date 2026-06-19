# Paper Portfolio Evidence Replay and Regression Gate

**Status:** v0.6.14 planning line
**Mode:** Paper-only
**Dependencies:** Offline / No-provider / No-broker / No-network
**Safety:** No real notification sending. No orders generated or submitted. Not financial advice. No live readiness. No profit guarantee.

## Purpose
The paper portfolio evidence replay and regression gate is the next step in the v0.6.14 portfolio evidence chain (CAND-006). Its purpose is to replay the proposal, stress, monitoring, recheck, and dossier processes multiple times to verify deterministic artifact stability and to ensure no hidden nondeterminism or schema drift has occurred. 

**This is not a live approval packet.**
This replay simply proves that the exact same artifacts can be dependably regenerated from the exact same input fixtures without volatile fields polluting the outcome.

## Inputs
To run the replay gate, provide:
- A deterministic sample data fixture (`--data`).
- A symbol to evaluate (`--symbol`).
- A list of strategies (`--strategies`).
- A repeat count indicating how many times to replay the chain (`--repeat`, default: 2).

## Output Artifacts
When the replay gate is completed, it produces:
1. **JSON Replay Report** (`paper-portfolio-replay.json`): A structured summary containing the stable digests for each run, the digest comparison results, and the overall replay status.
2. **Markdown Replay Report** (`paper-portfolio-replay.md`): A human-readable markdown version of the replay result.
3. **Regression Manifest JSON** (`paper-portfolio-regression-manifest.json`): A manifest tracking the overall replay digest and detailed run comparisons.
4. **Untracked Generated Artifacts**: Temporary JSON/MD artifacts from the underlying steps (proposal, stress, monitoring, recheck, dossier).

## Replay Decisions
The overall replay status will be one of the following:
- `paper_replay_pass`: All runs produced identical stable digests and schemas matched expectations.
- `paper_replay_drift_detected`: A mismatch was found in stable digests between runs.
- `paper_replay_schema_mismatch`: The generated artifacts did not match the expected schema version (e.g., version 1).
- `needs_recheck`: The replay was stable, but the underlying dossier indicated a recheck or watchlist was required.
- `rejected`: The replay was stable, but the underlying dossier was rejected.

## Stable Digest Rules
- The replay relies on computing a SHA-256 hash of the generated dictionaries (serialized with sorted keys).
- The `dossier` itself, along with the artifacts it bundles (`proposal`, `stress`, `monitoring`, `recheck`), are independently hashed.
- If the hashing reveals a difference between run 1 and run N, a `mismatch` is logged.
- The schema compatibility check ensures `schema_version == 1` inside the dossier.

## Safety Boundaries
- **No provider calls.**
- **No broker calls.**
- **No credentials.**
- **No live trading.**
- **No notifications sent.**
- **No orders generated.**
- **No autonomous live trading readiness.**

## Relationship to v0.6.14 CAND-001 through CAND-005
This replay gate validates the determinism of the paper portfolio evidence chain created in CAND-001 through CAND-005:
- [Paper Portfolio Proposal Sandbox](paper-portfolio-proposal.md)
- [Paper Portfolio Stress Constraints](paper-portfolio-stress.md)
- [Paper Portfolio Monitoring Simulation](paper-portfolio-monitoring.md)
- [Paper Portfolio Recheck Ledger](paper-portfolio-recheck-ledger.md)
- [Paper Portfolio Reviewer Dossier](paper-portfolio-dossier.md)
