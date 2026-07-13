# CAND-019: Docs/config hardcoded release-literal sweep

> **Status:** design for `v0.6.25` candidate chain  
> **Baseline public release:** `v0.6.24`  
> **Baseline package version:** `0.6.24`  
> **Baseline next planned release:** `v0.6.25`

## Goal

Extend `scripts/check_hardcoded_release_literals.py` so it also scans
example/config files for hardcoded release-identity literals. This catches
release drift in places that are easy to miss (example configs, example docs,
example code) before the next release cutover.

## Scope

### In scope

- `configs/*.yaml` (example broker/market/risk/provider/scheduler/strategy configs).
- `examples/**/*` (recursive: demo scripts, configs, docs).
- `docs/examples/**/*` (recursive example walkthroughs).
- Monitored literals derived from `docs/releases/release-metadata.json`:
  - `source_version` and its `v`-prefixed form (e.g. `0.6.24`, `v0.6.24`).
  - `current_public_release` and its non-`v` form.
  - `next_planned_release` and its non-`v` form.
- Reporting path, line number, literal value, and a short context snippet.
- Regression tests using temporary repositories.
- Integration into the existing dev/CI quick gate.

### Out of scope

- Scanning all `docs/**/*.md` prose files. Those are already covered by
  `scripts/check_public_docs_consistency.py` and often legitimately repeat the
  current release identity.
- Modifying release metadata, version strings, or tag state.
- Network access, credential loading, broker/provider calls, order submission,
  approval queue mutation, or runtime behavior changes.

## Design

### Architecture

The existing checker has two phases today:

1. Load monitored literals from `release-metadata.json`.
2. AST-walk every `scripts/*.py` file and report hardcoded literals.

CAND-019 adds a third phase:

3. Text-scan a configured list of docs/config example directories for the same
   monitored literals and report findings.

Phases 2 and 3 share the metadata-driven literal set but use separate scanners:

| Scanner | Input | Method | Files |
|---|---|---|---|
| Python AST scanner | existing | `ast.NodeVisitor` on `.py` files | `scripts/*.py` |
| Docs/config text scanner | new | regex line scan | `configs/`, `examples/`, `docs/examples/` |

If either scanner reports findings, the script exits `2` and prints a combined
report. If both are clean, it prints a single pass message summarizing the
script and docs/config scan counts and monitored literals.

### File and literal handling

- Only regular files are scanned. Symlinks and directories are skipped.
- Files are read as UTF-8; decode errors are treated as empty (no finding) with a
  warning to stderr.
- For each line, the scanner checks whether any monitored literal appears as a
  whole-word-ish substring. The regex is built by escaping each literal and
  joining with `|`. A negative lookbehind/lookahead for word characters is not
  used, because version literals can appear inside command examples like
  `v0.6.24` and we still want to flag them.
- Lines are reported with their 1-based line number and a 120-character snippet.

### Directories to scan

```python
DOCS_CONFIG_DIRS = [
    REPO_ROOT / "configs",
    REPO_ROOT / "examples",
    REPO_ROOT / "docs" / "examples",
]
```

### Output format

On failure, findings are grouped by scanner:

```text
Hardcoded release-literal check FAILED

Active scripts contain literals that should be metadata-driven:
  - scripts/some_checker.py:42 comparison literal '0.6.24'

Docs/config examples contain literals that should be metadata-driven:
  - configs/market.example.yaml:3 literal 'v0.6.24'  # market.symbol: ATLAS-DEMO-v0.6.24
```

On success:

```text
Hardcoded release-literal check PASSED
  Scanned 101 script file(s)
  Scanned 14 docs/config example file(s)
  Monitored literals: ['0.6.24', '0.6.25', 'v0.6.24', 'v0.6.25']
```

## Error handling

- Missing `release-metadata.json` is already a hard error from the existing
  metadata loader; the new scanner does not change this.
- Missing scan directories are treated as empty (no findings) so the checker can
  be run in a minimal test fixture.
- Unreadable files are skipped with a warning.
- AST parse errors in Python scripts remain skipped (existing behavior).

## Testing

New tests in `tests/test_check_hardcoded_release_literals.py`:

1. `test_docs_config_scan_finds_literal` — create a temp repo with a
   `configs/example.yaml` containing `v0.6.99`; assert `main() == 2` and output
   mentions the file.
2. `test_docs_config_scan_passes_when_clean` — create a temp repo with clean
   docs/config examples; assert `main() == 0`.
3. `test_scan_text_file_finds_literal` — unit test for the new
   `_scan_text_file` helper.
4. Existing tests continue to pass unchanged.

## Safety and governance

This candidate is a docs/checker/test-only change. It does not:

- enable live trading, live submit, order placement, broker/provider execution,
  credential loading, network access, or approval queue mutation;
- change `RiskManager`, kill switch, deadman, heartbeat, or audit hash-chain
  behavior;
- claim production readiness, profitability, or autonomous trading readiness;
- broaden the CAND-014 provider-artifact extraction boundary.

## Exit criteria

- `scripts/check_hardcoded_release_literals.py` scans `configs/`, `examples/`,
  and `docs/examples/`.
- New unit tests pass.
- `python3.11 scripts/check_hardcoded_release_literals.py` passes on the
  repository.
- `python3.11 -m pytest tests/test_check_hardcoded_release_literals.py -q`
  passes.
- Candidate is recorded in `docs/releases/v0.6.25-candidates.json` and
  `docs/releases/v0.6.25-candidates.md`.
