# Historical Release Checkers

These read-only checkers preserve release evidence for `v0.5.8` through
`v0.6.9`. They are retained for audit and regression testing, but they are not
active development or CI gates.

Run a historical checker directly from the repository root when investigating
its release:

```bash
python scripts/historical_release_checkers/check_v069_release_prep.py --release-prep
```

The active release-state checks are:

```bash
python scripts/check_v0610_release_prep.py --post-release
python scripts/check_v0611_planning.py
```

Archiving does not weaken or delete the historical checks. Their matching test
files remain in `tests/` and continue to run in the full test suite.
