#!/usr/bin/env bash
set -euo pipefail

# Atlas Agent — Product Demo Walkthrough
# Companion guide: docs/product-demo-pack.md
# Paper-only, offline, safe-by-default. No live trading, broker orders,
# provider calls, or credentials required.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(resolve_python_bin)"
require_python_311 "$PYTHON_BIN"

DEMO_SYMBOL="${DEMO_SYMBOL:-ATLAS-DEMO}"
BACKTEST_SYMBOL="${BACKTEST_SYMBOL:-DEMO-SYMBOL}"
SAMPLE_DATA="$REPO_ROOT/data/sample/ohlcv.csv"

if ! "$PYTHON_BIN" -c "import atlas_agent" >/dev/null 2>&1; then
  printf 'Missing prerequisite: atlas_agent is not installed. Run: %s -m pip install -e .\n' "$PYTHON_BIN" >&2
  exit 1
fi

if [ ! -f "$SAMPLE_DATA" ]; then
  printf 'Missing prerequisite: sample data not found at %s\n' "$SAMPLE_DATA" >&2
  exit 1
fi

usage() {
  printf 'Usage: %s [--keep-workspace] [--output-dir <path>] [--deterministic] [--no-output]\n' "${0##*/}"
  printf '  --keep-workspace   Do not delete the temporary demo workspace on exit.\n'
  printf '  --output-dir <path>   Generate a reviewable evidence bundle at <path>.\n'
  printf '  --deterministic       Use deterministic timestamps/ordering in the evidence bundle (for tests).\n'
  printf '  --no-output           Skip evidence generation even if --output-dir is set.\n'
  printf 'Environment:\n'
  printf '  DEMO_WORKSPACE                  Use this directory instead of a temp directory.\n'
  printf '  ATLAS_KEEP_PRODUCT_DEMO_DIR=1   Same as --keep-workspace.\n'
  printf '  ATLAS_PRODUCT_DEMO_DETERMINISTIC=1   Same as --deterministic.\n'
}

KEEP_WORKSPACE=0
OUTPUT_DIR=""
DETERMINISTIC=0
NO_OUTPUT=0
if [ "${ATLAS_KEEP_PRODUCT_DEMO_DIR:-}" = "1" ]; then
  KEEP_WORKSPACE=1
fi
if [ "${ATLAS_PRODUCT_DEMO_DETERMINISTIC:-}" = "1" ]; then
  DETERMINISTIC=1
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --keep-workspace)
      KEEP_WORKSPACE=1
      shift
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
    --no-output)
      NO_OUTPUT=1
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

if [ "$NO_OUTPUT" -eq 1 ] && [ -n "$OUTPUT_DIR" ]; then
  printf 'Error: --no-output and --output-dir are mutually exclusive\n' >&2
  usage >&2
  exit 1
fi

if [ -n "$OUTPUT_DIR" ]; then
  if [ -e "$OUTPUT_DIR" ]; then
    printf 'Refusing to reuse existing output directory: %s\n' "$OUTPUT_DIR" >&2
    exit 1
  fi
  mkdir -p "$OUTPUT_DIR/outputs"
fi

if [ -n "${DEMO_WORKSPACE:-}" ]; then
  WORKSPACE="$DEMO_WORKSPACE"
  if [ -e "$WORKSPACE" ]; then
    printf 'Refusing to reuse existing DEMO_WORKSPACE: %s\n' "$WORKSPACE" >&2
    exit 1
  fi
else
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-agent-product-walkthrough.XXXXXX")"
fi

cleanup() {
  if [ "$KEEP_WORKSPACE" -eq 0 ] && [ -z "${DEMO_WORKSPACE:-}" ]; then
    rm -rf "$WORKSPACE"
  fi
}
trap cleanup EXIT

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

atlas() {
  "$PYTHON_BIN" -m atlas_agent.cli "$@"
}

run_step() {
  printf '\n$ atlas %s\n' "$*"
  atlas "$@"
}

run_step_capture() {
  local name="$1"
  shift
  if [ -n "${OUTPUT_DIR:-}" ]; then
    printf '\n$ atlas %s\n' "$*" | tee -a "$OUTPUT_DIR/outputs/$name.txt"
    atlas "$@" 2>&1 | tee -a "$OUTPUT_DIR/outputs/$name.txt"
    printf '%s\n' "$*" >> "$OUTPUT_DIR/commands.txt"
  else
    printf '\n$ atlas %s\n' "$*"
    atlas "$@"
  fi
}

section_header() {
  local num="$1"
  local title="$2"
  local purpose="$3"
  printf '\n'
  printf -- '================================================================================\n'
  printf '  Section %s: %s\n' "$num" "$title"
  printf -- '================================================================================\n'
  printf '  Purpose: %s\n' "$purpose"
  printf '  Safety: paper-only; no credentials; no broker/provider calls; no live orders\n'
  printf -- '--------------------------------------------------------------------------------\n'
}

printf '================================================================================\n'
printf 'Atlas Agent — broker-neutral supervised trading workspace\n'
printf 'Package/source version: 0.6.11  (v0.6.12 is the planning line)\n'
printf 'License: MIT  |  Built by Natan Mucelli\n'
printf '================================================================================\n'
printf 'A local-first research and paper-trading workbench with\n'
printf 'deterministic safety gates, tamper-evident audit logs, and\n'
printf 'sandbox-only provider safety workflows.\n'
printf 'Default posture: paper-first, safe-by-default, broker-neutral.\n'
printf 'This walkthrough is sandbox/preflight-only. It does not enable\n'
printf 'live trading, submit broker orders, execute provider calls, or\n'
printf 'load credentials. Provider execution remains locked.\n'
printf 'Not financial advice. Trading involves significant risk of loss.\n'
printf 'Expected runtime: ~3–6 minutes\n'
printf '================================================================================\n'
printf '\nWorkspace: %s\n' "$WORKSPACE"
printf 'Symbol: %s\n' "$DEMO_SYMBOL"
printf 'Backtest symbol: %s\n' "$BACKTEST_SYMBOL"
printf 'Guide: docs/product-demo-pack.md\n'

section_header "1" "Create a sandbox workspace" \
  "Initialize an isolated temporary workspace from the routine-trader template."
cd "$REPO_ROOT"
run_step_capture init init "$WORKSPACE" --template routine-trader

section_header "2" "Configure safe discipline and demo symbol" \
  "Apply the default safe discipline profile and set the documentation-only symbol."
cd "$WORKSPACE"
run_step_capture discipline discipline setup --manual --yes
run_step_capture config-symbol config set market.symbol "$DEMO_SYMBOL"

section_header "3" "Validate paper mode and run redacted diagnostics" \
  "Confirm live trading is disabled and inspect local safety state without secrets."
run_step_capture validate validate
run_step_capture doctor doctor --json

section_header "4" "Run a paper dry-run" \
  "Print the planned paper workflow without contacting a broker or provider."
run_step_capture paper-dry-run run --mode paper --dry-run --symbol "$DEMO_SYMBOL"

section_header "5" "Run deterministic local backtest" \
  "Exercise the local backtest engine on bundled sample data."
run_step_capture backtest backtest run --symbol "$BACKTEST_SYMBOL" --data "$SAMPLE_DATA"

section_header "6" "Verify local artifacts" \
  "Validate backtest reports and audit manifests produced by the demo."
run_step_capture backtest-runs backtest runs --validate --json
run_step_capture audit audit verify --all

section_header "7" "What remains disabled" \
  "Confirm the demo did not enable any live or autonomous path."
printf '\nThis walkthrough is a paper/sandbox demonstration only.\n'
printf 'It does not enable or exercise any live execution path:\n'
printf '  - Live trading remains disabled by default.\n'
printf '  - Provider execution remains locked; no real LLM/provider calls are made.\n'
printf '  - Broker order submission is blocked (can_submit=false).\n'
printf '  - No broker credentials, API keys, or account identifiers are loaded.\n'
printf '  - Trust remains blocked for mock/provider safety artifacts.\n'
printf 'No live orders are submitted, no real money is at risk, and no\n'
printf 'autonomous trading, production readiness, or profitability is implied.\n'

section_header "8" "Next roadmap" \
  "Pointer to the public roadmap and upcoming planning work."
printf '\nAtlas is currently a paper-first, local research and simulation workspace.\n'
printf 'The public roadmap is documented in docs/v0.6-roadmap.md.\n'
printf 'Upcoming work focuses on safe, local tooling, not on enabling live trading.\n'
printf 'Safety defaults will not change: live trading stays disabled, provider\n'
printf 'execution stays locked, broker order submission stays blocked, and\n'
printf 'credentials are only loaded when explicitly configured by the operator.\n'
printf 'PyPI publish is not planned in this cycle.\n'

if [ -n "$OUTPUT_DIR" ] && [ "$NO_OUTPUT" -eq 0 ]; then
  section_header "9" "Build reviewable evidence bundle" \
    "Package captured outputs and artifact paths into a local evidence bundle."
  BUILDER_ARGS=(
    --output-dir "$OUTPUT_DIR"
    --workspace "$WORKSPACE"
    --commands-file "$OUTPUT_DIR/commands.txt"
  )
  if [ "$DETERMINISTIC" -eq 1 ]; then
    BUILDER_ARGS+=(--deterministic)
  fi
  printf '\n$ python %s' "$REPO_ROOT/scripts/build_product_demo_evidence.py"
  printf ' %s\n' "${BUILDER_ARGS[*]}"
  "$PYTHON_BIN" "$REPO_ROOT/scripts/build_product_demo_evidence.py" "${BUILDER_ARGS[@]}"
fi

printf '\nProduct walkthrough demo complete.\n'
if [ "$KEEP_WORKSPACE" -eq 1 ] || [ -n "${DEMO_WORKSPACE:-}" ]; then
  printf 'Review the workspace at: %s\n' "$WORKSPACE"
fi
if [ -n "$OUTPUT_DIR" ] && [ "$NO_OUTPUT" -eq 0 ]; then
  printf 'Review the evidence bundle at: %s\n' "$OUTPUT_DIR"
fi
printf 'This walkthrough was paper-only and local-only: no credentials loaded, no provider calls, no broker contact, and no live orders submitted.\n'
