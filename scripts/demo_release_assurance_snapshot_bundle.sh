#!/usr/bin/env bash
set -euo pipefail

# Atlas Agent — Release Assurance Bundle End-to-End Demo
# Companion guide: docs/security/release-assurance-bundle-demo.md
# Local-only, credential-free. No live trading, broker orders, provider calls,
# or tag/release/PyPI actions. Orchestrates release_assurance.py, which performs
# read-only local git/CLI checks; no credentials are loaded.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

DEFAULT_RELEASE="v0.6.12"
RELEASE="$DEFAULT_RELEASE"
OUTPUT_DIR=""
DETERMINISTIC=0

usage() {
  printf 'Usage: %s [OPTION]\n' "${0##*/}"
  printf '  --version <tag>     Release tag to assure (default: %s).\n' "$DEFAULT_RELEASE"
  printf '  --output-dir <path> Directory to write baseline/, with-reviewer-trust-snapshot/,\n'
  printf '                      and release-assurance-bundle-manifest.json.\n'
  printf '  --deterministic     Use deterministic timestamps for the reviewer trust snapshot.\n'
  printf '  --help, -h          Show this help message.\n'
  printf 'Environment:\n'
  printf '  ATLAS_RELEASE_ASSURANCE_DEMO_DETERMINISTIC=1  Same as --deterministic.\n'
}

if [ "${ATLAS_RELEASE_ASSURANCE_DEMO_DETERMINISTIC:-}" = "1" ]; then
  DETERMINISTIC=1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --version)
      if [ $# -lt 2 ]; then
        printf 'Option %s requires an argument\n' "$1" >&2
        usage >&2
        exit 1
      fi
      RELEASE="$2"
      shift 2
      ;;
    --output-dir)
      if [ $# -lt 2 ]; then
        printf 'Option %s requires an argument\n' "$1" >&2
        usage >&2
        exit 1
      fi
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --deterministic)
      DETERMINISTIC=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ -z "$OUTPUT_DIR" ]; then
  printf 'Error: --output-dir is required\n' >&2
  usage >&2
  exit 1
fi

if [ -e "$OUTPUT_DIR" ]; then
  if [ ! -d "$OUTPUT_DIR" ] || [ -n "$(ls -A "$OUTPUT_DIR" 2>/dev/null)" ]; then
    printf 'Refusing to reuse existing output directory: %s\n' "$OUTPUT_DIR" >&2
    exit 1
  fi
else
  mkdir -p "$OUTPUT_DIR"
fi

OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

BASELINE_DIR="$OUTPUT_DIR/baseline"
SNAPSHOT_DIR="$OUTPUT_DIR/with-reviewer-trust-snapshot"

printf '================================================================================\n'
printf 'Atlas Agent — Release Assurance Bundle Demo\n'
printf 'Release: %s\n' "$RELEASE"
printf 'Output:  %s\n' "$OUTPUT_DIR"
printf '================================================================================\n'
printf '\nThis demo is local-only and credential-free.\n'
printf 'It does not create tags, create GitHub releases, publish to PyPI, call\n'
printf 'providers, touch brokers, enable live trading, or load credentials.\n'
printf '\nRunning release assurance without reviewer trust snapshot...\n'

DETERMINISTIC_FLAG=""
if [ "$DETERMINISTIC" -eq 1 ]; then
  DETERMINISTIC_FLAG="--deterministic"
fi

"$PYTHON_BIN" "$REPO_ROOT/scripts/release_assurance.py" \
  --version "$RELEASE" \
  --output "$BASELINE_DIR"

if [ -d "$BASELINE_DIR/reviewer-trust-snapshot" ]; then
  printf 'FAIL: baseline bundle unexpectedly contains reviewer-trust-snapshot/\n' >&2
  exit 1
fi

printf '  -> baseline bundle OK (no reviewer trust snapshot)\n'
printf '\nRunning release assurance with --include-reviewer-trust-snapshot...\n'

"$PYTHON_BIN" "$REPO_ROOT/scripts/release_assurance.py" \
  --version "$RELEASE" \
  --output "$SNAPSHOT_DIR" \
  --include-reviewer-trust-snapshot

if [ ! -d "$SNAPSHOT_DIR/reviewer-trust-snapshot" ]; then
  printf 'FAIL: snapshot bundle is missing reviewer-trust-snapshot/\n' >&2
  exit 1
fi

printf '  -> snapshot bundle OK (reviewer trust snapshot included)\n'
printf '\nValidating reviewer trust snapshot in opt-in bundle...\n'

"$PYTHON_BIN" "$REPO_ROOT/scripts/check_reviewer_trust_snapshot.py" \
  "$SNAPSHOT_DIR/reviewer-trust-snapshot"

printf '  -> reviewer trust snapshot validation OK\n'
printf '\nBuilding release assurance bundle manifest...\n'

"$PYTHON_BIN" "$REPO_ROOT/scripts/build_release_assurance_bundle_manifest.py" \
  --baseline-dir "$BASELINE_DIR" \
  --snapshot-dir "$SNAPSHOT_DIR" \
  --release "$RELEASE" \
  --output-dir "$OUTPUT_DIR" \
  ${DETERMINISTIC_FLAG:+$DETERMINISTIC_FLAG}

printf '  -> manifest built OK\n'
printf '\nValidating release assurance bundle manifest...\n'

"$PYTHON_BIN" "$REPO_ROOT/scripts/check_release_assurance_bundle_manifest.py" \
  "$OUTPUT_DIR"

printf '  -> manifest validation OK\n'
printf '\n================================================================================\n'
printf 'Release assurance bundle demo complete.\n'
printf '  Baseline bundle:                  %s\n' "$BASELINE_DIR"
printf '  With reviewer trust snapshot:     %s\n' "$SNAPSHOT_DIR"
printf '  Manifest:                         %s/release-assurance-bundle-manifest.json\n' "$OUTPUT_DIR"
printf '================================================================================\n'
printf '\nNo tag, release, or PyPI publish was performed.\n'
printf 'The demo used release %s and ran entirely offline.\n' "$RELEASE"
