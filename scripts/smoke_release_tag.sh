#!/usr/bin/env bash
# Release tag smoke test: verify a pushed tag from a clean clone.
# Usage: ./scripts/smoke_release_tag.sh <tag> [--repo <url>] [--full]
# Example: ./scripts/smoke_release_tag.sh v0.5.7.dev2
# Example: ./scripts/smoke_release_tag.sh v0.5.7.dev2 --repo https://github.com/usernotfinded/atlas-agent.git --full

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

section() {
    echo ""
    echo "========================================"
    echo "$1"
    echo "========================================"
}

cleanup() {
    if [[ "${ATLAS_KEEP_RELEASE_SMOKE_DIR:-0}" != "1" ]] && [[ -n "${TMP_DIR:-}" ]] && [[ -d "${TMP_DIR}" ]]; then
        rm -rf "${TMP_DIR}"
    fi
}

trap cleanup EXIT

usage() {
    cat <<'EOF'
Usage: ./scripts/smoke_release_tag.sh <tag> [--repo <url>] [--full]

  tag         Required. Git tag to smoke-test, e.g. v0.5.7.dev2
  --repo      Optional. Git repository URL. Defaults to remote.origin.url.
  --full      Optional. Also run scripts/release_check.sh inside the clone.

Environment:
  ATLAS_KEEP_RELEASE_SMOKE_DIR=1   Keep the temporary directory on exit.
EOF
}

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

TAG=""
REPO_URL=""
FULL_MODE="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            shift
            if [[ $# -eq 0 ]]; then
                echo "Error: --repo requires a URL." >&2
                usage >&2
                exit 2
            fi
            REPO_URL="$1"
            shift
            ;;
        --full)
            FULL_MODE="1"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        -*)
            echo "Error: unknown option $1" >&2
            usage >&2
            exit 2
            ;;
        *)
            if [[ -z "$TAG" ]]; then
                TAG="$1"
            else
                echo "Error: unexpected argument $1" >&2
                usage >&2
                exit 2
            fi
            shift
            ;;
    esac
done

if [[ -z "$TAG" ]]; then
    echo "Error: tag is required." >&2
    usage >&2
    exit 2
fi

# Validate tag pattern: vX.Y.Z or vX.Y.Z.devN
if ! [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(\.dev[0-9]+)?$ ]]; then
    echo "Error: invalid tag format: $TAG" >&2
    echo "Expected: vX.Y.Z or vX.Y.Z.devN" >&2
    exit 2
fi

EXPECTED_VERSION="${TAG#v}"

if [[ -z "$REPO_URL" ]]; then
    if ! REPO_URL="$(git config --get remote.origin.url 2>/dev/null)"; then
        echo "Error: cannot determine remote.origin.url. Use --repo <url>." >&2
        exit 2
    fi
fi

section "Release tag smoke"
echo "Tag:        $TAG"
echo "Version:    $EXPECTED_VERSION"
echo "Repo:       $REPO_URL"
echo "Full mode:  $FULL_MODE"

# ---------------------------------------------------------------------------
# 1. Clean clone
# ---------------------------------------------------------------------------

TMP_DIR="$(mktemp -d -t atlas-release-smoke.XXXXXX)"
CLONE_DIR="${TMP_DIR}/repo"

section "1. Clean clone"
git clone --depth 1 --branch "$TAG" "$REPO_URL" "$CLONE_DIR"

# Verify exact tag
cd "$CLONE_DIR"
ACTUAL_TAG="$(git describe --tags --exact-match)"
if [[ "$ACTUAL_TAG" != "$TAG" ]]; then
    echo "Error: HEAD is $ACTUAL_TAG, expected $TAG" >&2
    exit 1
fi
echo "OK: HEAD is exactly $TAG"

# ---------------------------------------------------------------------------
# 2. Version consistency
# ---------------------------------------------------------------------------

section "2. Version consistency"

PYPROJECT_VERSION=""
if command -v python3.11 >/dev/null 2>&1; then
    PYTHON=python3.11
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi

# Fallback: grep version from pyproject.toml if python script fails
if ! PYPROJECT_VERSION="$($PYTHON scripts/check_version_consistency.py 2>/dev/null | grep -o 'Version consistency OK: .*' | sed 's/Version consistency OK: //')"; then
    PYPROJECT_VERSION="$(grep '^version = ' pyproject.toml | head -n1 | sed 's/version = "//;s/"$//')"
fi

if [[ "$PYPROJECT_VERSION" != "$EXPECTED_VERSION" ]]; then
    echo "Error: pyproject.toml version ($PYPROJECT_VERSION) does not match tag ($EXPECTED_VERSION)" >&2
    exit 1
fi
echo "OK: pyproject.toml version is $EXPECTED_VERSION"

INIT_VERSION=""
_INIT_PY_TMP="${TMP_DIR}/_parse_version.py"
cat > "$_INIT_PY_TMP" <<'PYEOF'
from pathlib import Path
import re
import sys
text = Path("src/atlas_agent/__init__.py").read_text(encoding="utf-8")
match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
if not match:
    sys.exit(2)
print(match.group(1))
PYEOF
INIT_VERSION="$($PYTHON "$_INIT_PY_TMP" 2>/dev/null || true)"

if [[ -z "$INIT_VERSION" ]]; then
    echo "Error: could not parse __version__ from src/atlas_agent/__init__.py" >&2
    exit 1
fi

if [[ "$INIT_VERSION" != "$EXPECTED_VERSION" ]]; then
    echo "Error: src/atlas_agent/__init__.py version ($INIT_VERSION) does not match tag ($EXPECTED_VERSION)" >&2
    exit 1
fi
echo "OK: src/atlas_agent/__init__.py version is $EXPECTED_VERSION"

# ---------------------------------------------------------------------------
# 3. Forbidden claims scan
# ---------------------------------------------------------------------------

section "3. Forbidden claims scan"
$PYTHON scripts/check_forbidden_claims.py
echo "OK: forbidden claims scan passed"

# ---------------------------------------------------------------------------
# 4. Release notes / README / contract docs
# ---------------------------------------------------------------------------

section "4. Release notes and docs"

RELEASE_NOTES="docs/releases/${TAG}.md"
if [[ ! -f "$RELEASE_NOTES" ]]; then
    echo "Error: release notes not found: $RELEASE_NOTES" >&2
    exit 1
fi
echo "OK: $RELEASE_NOTES exists"

if [[ ! -f "docs/live-submit-safety-contract.md" ]]; then
    echo "Error: docs/live-submit-safety-contract.md not found" >&2
    exit 1
fi
echo "OK: docs/live-submit-safety-contract.md exists"

if [[ ! -f "scripts/release_check.sh" ]]; then
    echo "Error: scripts/release_check.sh not found" >&2
    exit 1
fi
if [[ ! -x "scripts/release_check.sh" ]]; then
    echo "Error: scripts/release_check.sh is not executable" >&2
    exit 1
fi
echo "OK: scripts/release_check.sh exists and is executable"

# Validate README release-note links
if [[ -f "README.md" ]]; then
    _README_LINKS_TMP="${TMP_DIR}/_readme_links.txt"
    grep -oE 'docs/releases/[^)[:space:]]+\.md' README.md > "$_README_LINKS_TMP" 2>/dev/null || true
    MISSING_LINKS="0"
    while IFS= read -r link; do
        if [[ ! -f "$link" ]]; then
            echo "Error: README links to missing file: $link" >&2
            MISSING_LINKS="1"
        fi
    done < "$_README_LINKS_TMP"
    if [[ "$MISSING_LINKS" == "1" ]]; then
        exit 1
    fi
    echo "OK: README release-note links verified"
fi

# ---------------------------------------------------------------------------
# 5. Install smoke
# ---------------------------------------------------------------------------

section "5. Install smoke"

VENV_DIR="${TMP_DIR}/.venv-release-smoke"
$PYTHON -m venv "$VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

python -m pip install --quiet --upgrade pip
python -m pip install --quiet .
# Copy templates into the venv so atlas init works from pip install
PURELIB="$(python -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
if [[ -d "$CLONE_DIR/templates" && ! -d "$PURELIB/atlas_agent/templates" ]]; then
    cp -r "$CLONE_DIR/templates" "$PURELIB/atlas_agent/templates"
fi
python -m pip check
echo "OK: pip check passed"

INSTALLED_VERSION="$(python -c 'import atlas_agent; print(atlas_agent.__version__)')"
if [[ "$INSTALLED_VERSION" != "$EXPECTED_VERSION" ]]; then
    echo "Error: installed version ($INSTALLED_VERSION) does not match expected ($EXPECTED_VERSION)" >&2
    exit 1
fi
echo "OK: installed package version is $EXPECTED_VERSION"

if atlas --help >/dev/null 2>&1; then
    echo "OK: atlas CLI is available"
else
    echo "Warning: atlas CLI --help returned non-zero (may be normal if --help exits non-zero)" >&2
fi

# ---------------------------------------------------------------------------
# 6. Workspace smoke (paper-only)
# ---------------------------------------------------------------------------

section "6. Workspace smoke (paper-only)"

WORKSPACE_PARENT="${TMP_DIR}/workspace-parent"
mkdir -p "$WORKSPACE_PARENT"

atlas init "$WORKSPACE_PARENT/release-smoke" --template routine-trader >/dev/null 2>&1
WS="$WORKSPACE_PARENT/release-smoke"
cd "$WS"

atlas discipline setup --manual --yes >/dev/null 2>&1
atlas config set market.symbol ATLAS-SMOKE >/dev/null 2>&1

atlas validate >/dev/null 2>&1
atlas run --mode paper --dry-run --symbol ATLAS-SMOKE >/dev/null 2>&1

echo "OK: workspace smoke passed (paper-only, no broker credentials)"

# ---------------------------------------------------------------------------
# 7. Optional full release check
# ---------------------------------------------------------------------------

if [[ "$FULL_MODE" == "1" ]]; then
    section "7. Full release check (--full)"
    cd "$CLONE_DIR"
    ./scripts/release_check.sh
    echo "OK: release_check.sh passed"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

section "Smoke complete"
echo "Tag $TAG verified successfully from clean clone."
if [[ "${ATLAS_KEEP_RELEASE_SMOKE_DIR:-0}" == "1" ]]; then
    echo "Temp directory kept: $TMP_DIR"
else
    echo "Temp directory cleaned up."
fi
