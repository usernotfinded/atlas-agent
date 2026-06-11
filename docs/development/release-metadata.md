# Release Metadata

Atlas Agent manages release status, source versions, and public release tags using a canonical JSON metadata file: `docs/releases/release-metadata.json`.

## Purpose

The metadata file establishes a single source of truth for release scripts, tests, and CI/CD gates. By decoupling the versioning facts from the checker scripts themselves, we avoid brittle hardcoding of current release names inside testing infrastructure.

## Schema

- `schema_version`: Data structure version integer.
- `source_version`: The package version that the `main` branch currently represents (e.g. "0.6.9"). Must match `pyproject.toml`.
- `current_public_release`: The exact Git tag for the latest stable, officially published release.
- `next_planned_release`: Advisory target for the next release line.
- `pypi_published`: Repository-level toggle indicating if PyPI publication is globally enabled and executed.
- `releases`: An array of recent stable and prepared releases, linking to their respective release notes and trust center status documents.

## Releasing and Cutovers

When preparing a new release candidate or cutting a stable tag, `release-metadata.json` must be updated *before* or *alongside* the cutover commit. Checkers will ensure that `current_public_release` points to a tag with `status: "current_public"`, and that release notes exist.

## PyPI Status

`pypi_published` remains explicit and false for all releases and overall repository configuration unless PyPI distribution is explicitly approved by project policy.

## Script Integration

- `scripts/release_metadata.py`: Exposes schema validation and helper methods to load metadata.
- `scripts/check_release_metadata.py`: Standalone CLI validator to ensure the JSON strictly complies with safety and integrity standards. This runs in local preflight checks (`dev_check.sh`) and GitHub Actions (`ci_check.sh`).
- `scripts/check_version_consistency.py`: Reads the metadata to determine the expected values during its checks against the package, README, and CHANGELOG.
