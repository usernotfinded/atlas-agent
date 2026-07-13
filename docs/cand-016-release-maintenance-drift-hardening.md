# CAND-016 — Release-Maintenance Drift Hardening

> **Status:** accepted into the `v0.6.22` candidate chain on 2026-07-13 with verdict **PASS** (not released)
> **Release line:** `v0.6.22` (planning-only)
> **Current public release:** `v0.6.21` · **Previous:** `v0.6.20` · **Next planned:** `v0.6.22`
> **PyPI:** not published · **Tag created:** no · **GitHub Release:** not created
> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## Summary

CAND-016 hardens the **release-maintenance path** so that release-identity state
(current/previous/next release, which candidates shipped where, and demo/tooling
defaults) stays synchronized with `docs/releases/release-metadata.json` instead of
drifting behind hardcoded version literals. It is a docs/checker/test-only
candidate: it adds no runtime, trading, broker, provider, or credential behavior.

## Context — the post-release drift this addresses

The `v0.6.21` cutover and its post-release stabilization surfaced three concrete
release-maintenance drift classes, all caused by hardcoded release literals that a
"bump everything by one" cutover step must keep in sync by hand:

1. **Next-planned tag guard drift.** Three checkers guarded `git tag --list
   <literal>`; one literal was left at `v0.6.21` after the next-planned line moved
   to `v0.6.22`, and it only fails *after* the tag is created. Fixed post-release
   by making the guard read `NEXT_PLANNED_TAG` from metadata.
2. **Stale demo default.** `scripts/demo_release_assurance_snapshot_bundle.sh`
   hardcoded `DEFAULT_RELEASE="v0.6.15"`; its `package_version_aligned` check then
   compared `pyproject`/`__init__` (`0.6.21`) against `0.6.15` and failed on the
   first post-release full-suite CI run. Fixed by reading
   `current_public_release` from metadata.
3. **Roadmap candidate mislabeling.** The cutover's blind version increment moved
   `docs/autonomy-roadmap.md` candidate sections forward by one, so already-released
   candidates (CAND-013/014/015) were listed under the `v0.6.22` planning line and
   CAND-012 was mislabeled as `v0.6.21`. The existing consistency checker only
   caught the *forward* case ("roadmap says no candidates while the chain has
   accepted ones"), not this *reverse* case.

CAND-016 makes these guards metadata-driven and adds coverage for the reverse
drift so the class of bug cannot silently return.

## Design

- **Reverse-drift roadmap guard (delivered).** `scripts/check_public_docs_consistency.py`
  gains `_released_candidate_ids()` (reads candidate IDs recorded as
  accepted/released in the current public release and any `historical` release
  line from metadata) and
  `_check_autonomy_roadmap_released_candidates_not_next_planned()`, which flags any
  already-released candidate listed as a **candidate-entry bullet** (`- CAND-XXX …`)
  under the `<next_planned>` planning-line section of the roadmap. Prose
  cross-references to a released candidate are intentionally ignored to avoid
  false positives. The check is a no-op when there are no released candidate IDs
  or when the doc is not the roadmap. Exit codes `0`/`1` are unchanged.
- **Metadata-driven demo default (delivered).** The release-assurance snapshot
  demo derives its default release from `current_public_release` with a pinned
  fallback, so it assures the current release and never goes stale.
- **Both draw their release-identity facts from `release-metadata.json`**, which
  remains the single source of truth. Deliberate version-pin tripwire assertions
  in per-release checkers (e.g. `if CURRENT_PUBLIC_TAG != "v0.6.21"`) are **left
  as-is**: they are meant to fail at cutover to force a review, and making them
  read metadata would render them tautological.

## Implementation plan

1. Add `_released_candidate_ids()` and the reverse-drift roadmap check to
   `check_public_docs_consistency.py`, wired into `main()`. *(done)*
2. Add focused, deterministic tests in `tests/test_public_docs_consistency.py`
   covering: released bullet under next-planned (fails), multiple released
   candidates (each flagged), proposed candidate (passes), prose mention
   (passes), released candidate under its own release section (passes), empty
   released set / non-roadmap path (no-op), and `_released_candidate_ids()`
   reading released lines from a fixture repo. *(done)*
3. Keep the metadata-driven demo default from the post-release stabilization
   pass. *(done)*
4. Follow-up (not required for this candidate): a lint/guard that scans
   release-maintenance scripts for newly introduced hardcoded current-release
   literals, so metadata-driven defaults cannot regress. *(future, out of scope
   for CAND-016)*

## Safety boundaries

CAND-016 changes only a static documentation checker, its tests, a demo default,
and planning documentation. It does not, and must not:

- enable live trading or make live trading a default;
- enable live order submission or change `can_submit`;
- enable broker/provider execution, or call real brokers or providers;
- load broker/provider credentials;
- add network access (checkers read local files only);
- place, cancel, or flatten orders, or create pending orders;
- mutate approval queues, the kill switch, heartbeat, deadman, or the audit
  hash-chain;
- change `RiskManager` behavior;
- broaden the CAND-014 provider-artifact extraction boundary (which stays strictly
  `src/atlas_agent/research/provider_mock_response_final_safety_seal.py`);
- weaken or remove the deliberate version-pin tripwire assertions.

`atlas run --mode live` remains fail-closed. This is a GitHub-only project; PyPI
remains unpublished.

## Acceptance criteria

- `check_public_docs_consistency.py` exits `0` on the current repository and
  exits `1` with a clear message when a released candidate is listed as a
  candidate-entry bullet under the next-planned planning-line section.
- The reverse-drift check is metadata-driven (released IDs and next-planned tag
  come from `release-metadata.json`) and is not pinned to a specific release
  number.
- No false positive on prose mentions of released candidates or on released
  candidates under their own release section.
- Deterministic tests cover the forward-fixed cases and the new reverse case and
  pass offline with no network or credentials.
- All existing required checks (`dev_check.sh`, `ci_check.sh`,
  `release_check.sh --quick`) remain green.
- No runtime, safety, broker, provider, credential, version, or release-metadata
  behavior changes; no tag, GitHub Release, or PyPI publication.

## Non-goals

- Not a release cutover; no version bump, tag, GitHub Release, or PyPI publish.
- Not a change to any runtime trading, broker, provider, or safety module.
- Not a rewrite of the per-release version-pin tripwires into metadata reads.
- Not an expansion of the CAND-014 extraction boundary.
- Not a live-readiness, production-readiness, unattended-safety, or profitability
  claim of any kind.

## Relationship to CAND-013/014/015

CAND-016 extends the public/trust docs drift coverage guard first shipped as
CAND-013 by adding the reverse-drift direction. It preserves the CAND-014
single-module pilot boundary and does not touch provider-artifact code. It leaves
CAND-015 evidence-only, with its clean-room independence caveat preserved in the
`v0.6.21` release history; no external or human review evidence is claimed or
invented for CAND-016.
