# Release Checker Hardcoding Audit

## Overview
This document tracks the final repository-wide audit of hardcoded release state references (e.g. version numbers and tags) across all verification scripts in `scripts/`. 

The goal of this migration was to consolidate authoritative release state into `docs/releases/release-metadata.json` so that active checkers do not require manual version bumping during the release process, while intentionally preserving historical release checkers to guarantee past release safety states.

## Migrated Scripts (Active Checkers)
The following scripts check current release constraints. They have been migrated to load their release state dynamically from `docs/releases/release-metadata.json` via the `ReleaseMetadata` class:

* `scripts/build_release_evidence_bundle.py`
* `scripts/check_clean_install.py`
* `scripts/check_final_rc_audit.py`
* `scripts/check_onboarding_docs.py`
* `scripts/check_package_distribution.py`
* `scripts/check_public_docs_consistency.py`
* `scripts/check_public_launch_messaging.py`
* `scripts/check_public_launch_readiness.py`
* `scripts/check_reviewer_onboarding.py`
* `scripts/check_stable_release_decision.py`
* `scripts/check_trust_center.py`
* `scripts/main_health.py`

*(Note: `scripts/check_v0581_hotfix_cutover.py` was also migrated to use dynamic version checking as it actively verified the current repository state against the `EXPECTED_VERSION`.)*

## Static / Historical Scripts (Preserved)
The following scripts perform checks against specific historical contexts, versions, or tags. They have deliberately been left untouched to maintain historical CI guarantees and prevent regression testing drift.

* `scripts/check_v058_rc1_readiness.py` (Checks v0.5.8 RC1)
* `scripts/check_v061_release_prep.py` (Checks v0.6.1 prep)
* `scripts/check_v062_release_prep.py` (Checks v0.6.2 prep)
* `scripts/check_v063_release_prep.py` (Checks v0.6.3 prep)
* `scripts/check_v068_release_prep.py` (Checks v0.6.8 prep)
* `scripts/check_v069_release_prep.py` (Checks v0.6.9 prep)
* `scripts/check_rc1_cutover.py` (Verifies historical RC cutover patterns)
* `scripts/check_demo_command_smoke.py` (References specific v0.6.8 candidate files)
* `scripts/check_demo_proof.py` (Validates explicit string references to "v0.6.8 release notes" in documentation)
* `scripts/check_generated_artifacts.py` (Contains a static allowlist of historical `TRACKED_VERSIONED_EVIDENCE_PREFIXES` up to `v0.6.9`)

## Conclusion
Active continuous integration checkers now successfully reference `docs/releases/release-metadata.json` dynamically. Tests have been updated to assert proper metadata loads instead of searching for hardcoded strings. All tests and CI checks are green.
