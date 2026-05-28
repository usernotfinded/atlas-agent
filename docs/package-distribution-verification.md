# Package Distribution Verification

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

## What this checks

The package distribution verification script (`scripts/check_package_distribution.py`) performs a **local-only** dry-run to confirm that Atlas Agent can be built as distribution artifacts (wheel and sdist) and that their metadata is correct, without publishing or uploading anything.

It answers:

> "Can this repo produce distribution artifacts locally and verify their metadata safely, without publishing or uploading anything?"

## What it does not do

- **Does not publish** to PyPI.
- **Does not upload** packages anywhere.
- **Does not create** GitHub releases.
- **Does not push** tags.
- **Does not change** live trading behavior.
- **Does not enable** provider execution.
- **Does not enable** broker execution.
- **Does not load** credentials.
- **Does not make** network calls inside Atlas runtime.
- **Does not modify** risk gates.

## Dry-run mode

```bash
python3.11 scripts/check_package_distribution.py --dry-run
```

Prints the planned steps without creating artifacts:

- Build plan (sdist + wheel)
- Metadata checks planned
- Artifact verification planned
- Cleanup planned

Exit code `0`.

## Local artifact build mode

```bash
python3.11 scripts/check_package_distribution.py
```

Default behavior:

1. Creates a temporary output directory.
2. Runs `python -m build --sdist --wheel --outdir <temp>` if the `build` module is available.
3. Verifies one wheel and one sdist exist.
4. Verifies package name is `atlas-agent` (or normalized equivalent).
5. Verifies package version metadata matches `0.5.7rc4`.
6. Verifies artifact filenames correspond to `0.5.7rc4` or normalized equivalent.
7. Verifies the `atlas` console entry point is declared.
8. Optionally runs `twine check` if `twine` is available.
9. Removes generated artifacts when done.
10. Reports only safe, redacted paths.

If `build` or `twine` is not available, the script reports the missing dependency clearly and exits non-zero.

Optional flags:
- `--allow-network-build` to permit `python -m build` to fetch build dependencies from PyPI. Default is no-network.
- `--keep-artifacts` to preserve the temporary build directory.
- `--output-dir <path>` to use a specific output directory instead of a temporary one.
- `--skip-twine` to skip the twine check even if twine is installed.

## Metadata checks

The script inspects generated artifacts safely:

- **Wheel METADATA**: read directly from the `.whl` zipfile.
- **Entry points**: checked via `entry_points.txt` inside the wheel.
- **Sdist**: inspected via `tarfile` without extracting to disk.
- **Version**: must match the expected package version.
- **Name**: must match the expected normalized package name.

No untrusted archive paths are extracted directly. Path traversal is guarded against.

## Safety limits

- No `shell=True` in subprocess calls.
- No `git push`, `git tag`, `gh release create`, or `twine upload`.
- Default build uses `--no-isolation` to avoid network dependency resolution.
- No credential loading.
- No broker or provider contact.
- Output redacts absolute paths (`<repo>`, `<temp>`, `<home>`, `<users>`, `<dist>`).
- Subprocess failure output is redacted before printing.

## How to clean artifacts

By default, the script uses a temporary output directory and deletes it on success or failure.

To keep artifacts for debugging:

```bash
python3.11 scripts/check_package_distribution.py --keep-artifacts
```

To specify a custom output directory:

```bash
python3.11 scripts/check_package_distribution.py --output-dir ./tmp-dist
```

If you manually create `dist/` or `build/` locally, ensure they are not staged:

```bash
git status
# Do not run: git add dist/ build/ *.egg-info/
```

## Why this is separate from publishing

Publishing (PyPI upload, GitHub release, tag push) is a separate, human-gated step that happens only after:

- All local verification passes.
- Protected boundaries are confirmed clean.
- External review is complete.
- An explicit PUSH OK is granted.

This script provides a safe, automated preflight that catches packaging issues before any publish step is considered.

## Live trading and safety posture

- Live trading remains **disabled by default**.
- Provider execution remains **locked**.
- Trust remains **blocked**.
- No broker/order path is enabled by this workflow.
- No credentials are loaded.
- This is a **sandbox/paper/preflight** verification step only.
- Safety validation does not imply profitability or trading correctness.
