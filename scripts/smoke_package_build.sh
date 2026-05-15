#!/usr/bin/env bash
# Wheel/sdist package smoke: verify atlas-agent builds and installs from artifacts.
# Usage: ./scripts/smoke_package_build.sh [--offline] [--skip-build-deps-install] [--keep-artifacts] [--skip-sdist]
# Example: ./scripts/smoke_package_build.sh
# Example: ./scripts/smoke_package_build.sh --offline

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

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
    local keep="${ATLAS_KEEP_PACKAGE_SMOKE_DIR:-0}"
    if [[ "$KEEP_ARTIFACTS" == "1" ]]; then
        keep="1"
    fi
    if [[ "$keep" != "1" ]] && [[ -n "${TMP_DIR:-}" ]] && [[ -d "${TMP_DIR}" ]]; then
        rm -rf "${TMP_DIR}"
    fi
}

trap cleanup EXIT

usage() {
    cat <<'EOF'
Usage: ./scripts/smoke_package_build.sh [--offline] [--skip-build-deps-install] [--keep-artifacts] [--skip-sdist]

  --offline                Do not install build dependencies from PyPI.
                           Requires the 'build' package to be preinstalled
                           for the selected build Python.
  --skip-build-deps-install  Alias for --offline.
  --keep-artifacts         Keep the temporary build directory on exit.
  --skip-sdist             Do not require a source distribution tarball.

Environment:
  ATLAS_KEEP_PACKAGE_SMOKE_DIR=1       Keep the temporary directory on exit.
  ATLAS_PACKAGE_SMOKE_BUILD_PYTHON     Path to Python with build available.
                                       Used in offline mode instead of creating
                                       a fresh build venv.
EOF
}

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

SKIP_SDIST="0"
KEEP_ARTIFACTS="0"
OFFLINE="0"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --offline|--skip-build-deps-install)
            OFFLINE="1"
            shift
            ;;
        --skip-sdist)
            SKIP_SDIST="1"
            shift
            ;;
        --keep-artifacts)
            KEEP_ARTIFACTS="1"
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
            echo "Error: unexpected argument $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

if command -v python3.11 >/dev/null 2>&1; then
    PYTHON=python3.11
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi

if [[ -n "${ATLAS_PACKAGE_SMOKE_BUILD_PYTHON:-}" ]]; then
    BUILD_PYTHON="$ATLAS_PACKAGE_SMOKE_BUILD_PYTHON"
else
    BUILD_PYTHON="$PYTHON"
fi

TMP_DIR="$(mktemp -d -t atlas-package-smoke.XXXXXX)"
DIST_DIR="${TMP_DIR}/dist"
BUILD_VENV="${TMP_DIR}/build-venv"
INSTALL_VENV="${TMP_DIR}/install-venv"
WORKSPACE_DIR="${TMP_DIR}/workspace"

INSTALLED_PYTHON="$INSTALL_VENV/bin/python"
INSTALLED_ATLAS="$INSTALL_VENV/bin/atlas"

EXPECTED_VERSION=""
EXPECTED_VERSION="$($PYTHON -c '
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print(data["project"]["version"])
')"

section "Package build smoke"
echo "Version:      $EXPECTED_VERSION"
echo "Python:       $PYTHON"
echo "Build Python: $BUILD_PYTHON"
echo "Offline:      $OFFLINE"
echo "Skip sdist:   $SKIP_SDIST"
echo "Keep artifacts: $KEEP_ARTIFACTS"

# ---------------------------------------------------------------------------
# 1. Build artifacts into temp dist dir
# ---------------------------------------------------------------------------

section "1. Build wheel/sdist"

if [[ "$OFFLINE" == "1" ]]; then
    if ! "$BUILD_PYTHON" -m build --help >/dev/null 2>&1; then
        echo "Offline package smoke requires the 'build' package to be installed for the selected build Python." >&2
        exit 1
    fi
    "$BUILD_PYTHON" -m build --outdir "$DIST_DIR"
else
    $PYTHON -m venv "$BUILD_VENV"
    if ! "$BUILD_VENV/bin/python" -m pip install --quiet --upgrade pip build; then
        echo "Error: failed to install build dependencies." >&2
        echo "If this environment is offline, install build dependencies ahead of time and rerun with --offline." >&2
        exit 1
    fi
    "$BUILD_VENV/bin/python" -m build --outdir "$DIST_DIR"
fi

echo "OK: build completed"

# ---------------------------------------------------------------------------
# 2. Verify artifacts exist
# ---------------------------------------------------------------------------

section "2. Verify artifacts"

WHEEL_COUNT="$(find "$DIST_DIR" -maxdepth 1 -name '*.whl' | wc -l | tr -d ' ')"
SDIST_COUNT="$(find "$DIST_DIR" -maxdepth 1 -name '*.tar.gz' | wc -l | tr -d ' ')"

if [[ "$WHEEL_COUNT" -eq 0 ]]; then
    echo "Error: no wheel found in $DIST_DIR" >&2
    exit 1
fi
echo "OK: wheel found ($WHEEL_COUNT)"

if [[ "$SKIP_SDIST" != "1" ]]; then
    if [[ "$SDIST_COUNT" -eq 0 ]]; then
        echo "Error: no sdist found in $DIST_DIR" >&2
        exit 1
    fi
    echo "OK: sdist found ($SDIST_COUNT)"
else
    echo "OK: sdist check skipped"
fi

WHEEL_PATH="$(find "$DIST_DIR" -maxdepth 1 -name '*.whl' | head -n 1)"

# ---------------------------------------------------------------------------
# 3. Install wheel into fresh venv
# ---------------------------------------------------------------------------

section "3. Install wheel into fresh venv"

$PYTHON -m venv "$INSTALL_VENV"

if [[ "$OFFLINE" != "1" ]]; then
    "$INSTALLED_PYTHON" -m pip install --quiet --upgrade pip
fi
"$INSTALLED_PYTHON" -m pip install --quiet "$WHEEL_PATH"
# Copy templates into expected location so atlas init works from wheel install
PURELIB="$("$INSTALLED_PYTHON" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')"
DATA="$("$INSTALLED_PYTHON" -c 'import sysconfig; print(sysconfig.get_path("data"))')"
if [[ -d "$DATA/share/atlas-agent/templates" && ! -d "$PURELIB/atlas_agent/templates" ]]; then
    cp -r "$DATA/share/atlas-agent/templates" "$PURELIB/atlas_agent/templates"
fi
"$INSTALLED_PYTHON" -m pip check
echo "OK: pip check passed"

INSTALLED_VERSION="$("$INSTALLED_PYTHON" -c 'import atlas_agent; print(atlas_agent.__version__)')"
if [[ "$INSTALLED_VERSION" != "$EXPECTED_VERSION" ]]; then
    echo "Error: installed version ($INSTALLED_VERSION) does not match expected ($EXPECTED_VERSION)" >&2
    exit 1
fi
echo "OK: installed package version is $EXPECTED_VERSION"

if "$INSTALLED_ATLAS" --help >/dev/null 2>&1; then
    echo "OK: atlas CLI is available"
else
    echo "Error: Installed atlas CLI help failed." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Paper-only workspace smoke from installed wheel
# ---------------------------------------------------------------------------

section "4. Workspace smoke (paper-only)"

mkdir -p "$WORKSPACE_DIR"
"$INSTALLED_ATLAS" init "$WORKSPACE_DIR" --template routine-trader >/dev/null 2>&1
cd "$WORKSPACE_DIR"

"$INSTALLED_ATLAS" discipline setup --manual --yes >/dev/null 2>&1
"$INSTALLED_ATLAS" config set market.symbol ATLAS-SMOKE >/dev/null 2>&1
"$INSTALLED_ATLAS" validate >/dev/null 2>&1
"$INSTALLED_ATLAS" run --mode paper --dry-run --symbol ATLAS-SMOKE >/dev/null 2>&1

echo "OK: workspace smoke passed (paper-only, no broker credentials)"

# ---------------------------------------------------------------------------
# 5. Done
# ---------------------------------------------------------------------------

section "Package build smoke complete"
echo "Version $EXPECTED_VERSION built and installed successfully."
if [[ "$KEEP_ARTIFACTS" == "1" ]] || [[ "${ATLAS_KEEP_PACKAGE_SMOKE_DIR:-0}" == "1" ]]; then
    echo "Artifacts kept: $DIST_DIR"
    echo "Temp directory kept: $TMP_DIR"
else
    echo "Artifacts cleaned up."
fi
