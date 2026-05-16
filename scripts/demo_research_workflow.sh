#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
DEMO_SYMBOL="${DEMO_SYMBOL:-ATLAS-DEMO}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  printf 'Missing prerequisite: %s is not available on PATH.\n' "$PYTHON_BIN" >&2
  exit 1
fi

KEEP_WORKSPACE=0
if [ "${1:-}" = "--keep-workspace" ] || [ "${ATLAS_KEEP_RESEARCH_DEMO_DIR:-}" = "1" ]; then
  KEEP_WORKSPACE=1
fi

if [ -n "${DEMO_WORKSPACE:-}" ]; then
  WORKSPACE="$DEMO_WORKSPACE"
else
  WORKSPACE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-research-demo.XXXXXX")"
fi

cleanup() {
  if [ "$KEEP_WORKSPACE" -eq 0 ]; then
    rm -rf "$WORKSPACE"
  else
    printf 'Workspace retained at: %s\n' "$WORKSPACE"
  fi
}
trap cleanup EXIT

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

atlas() {
  if [ -n "${ATLAS_BIN:-}" ]; then
    "$ATLAS_BIN" "$@"
  else
    "$PYTHON_BIN" -m atlas_agent.cli "$@"
  fi
}

run_step() {
  printf '\n$ atlas %s\n' "$*"
  atlas "$@"
}

json_field() {
  local json="$1"
  local field="$2"
  "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
for part in '$field'.split('.'):
    data=data[part]
print(data)
" <<<"$json"
}

json_bool() {
  local json="$1"
  local field="$2"
  "$PYTHON_BIN" -c "import json,sys; print(json.load(sys.stdin)['$field'])" <<<"$json"
}

assert_ok() {
  local json="$1"
  local label="$2"
  local ok
  ok="$(json_bool "$json" ok)"
  if [ "$ok" != "True" ]; then
    printf 'FAIL: %s returned ok=false\n' "$label" >&2
    exit 1
  fi
}

assert_file_exists() {
  local path="$1"
  local label="$2"
  if [ ! -f "$path" ]; then
    printf 'FAIL: %s file not found: %s\n' "$label" "$path" >&2
    exit 1
  fi
}

assert_no_pending_orders() {
  if [ -d "$WORKSPACE/pending_orders" ]; then
    local files
    files="$(find "$WORKSPACE/pending_orders" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null || true)"
    if [ -n "$files" ]; then
      printf 'FAIL: Research demo created pending orders unexpectedly.\n' >&2
      exit 1
    fi
  fi
}

assert_no_absolute_paths() {
  local text="$1"
  if grep -q '/Users/' <<<"$text"; then
    printf 'FAIL: Output contains absolute /Users/ path.\n' >&2
    exit 1
  fi
  if grep -q '/private/var/' <<<"$text"; then
    printf 'FAIL: Output contains absolute /private/var/ path.\n' >&2
    exit 1
  fi
}

assert_no_secrets_in_output() {
  local text="$1"
  if grep -qiE 'Authorization:|Bearer |sk-[a-zA-Z0-9]{10,}|pplx-[a-zA-Z0-9]{10,}' <<<"$text"; then
    printf 'FAIL: Output may contain secret-like content.\n' >&2
    exit 1
  fi
}

printf 'Atlas Agent research workflow demo\n'
printf 'Workspace: %s\n' "$WORKSPACE"
printf 'Symbol: %s\n' "$DEMO_SYMBOL"
printf 'This demo is paper-only and does not require broker credentials.\n'

cd "$REPO_ROOT"
run_step init "$WORKSPACE" --template routine-trader

cd "$WORKSPACE"
run_step discipline setup --manual --yes
run_step config set market.symbol "$DEMO_SYMBOL"

# Create deterministic sample data for evaluation
mkdir -p "$WORKSPACE/data"
cat > "$WORKSPACE/data/ohlcv.csv" <<'CSV'
timestamp,open,high,low,close,volume
2026-01-01,100,105,99,104,1000
2026-01-02,104,106,101,102,1200
2026-01-03,102,108,101,107,1300
CSV

# 1. Research run
printf '\n--- Research run ---\n'
RUN_OUTPUT="$(atlas research run --symbol "$DEMO_SYMBOL" --json)"
assert_no_absolute_paths "$RUN_OUTPUT"
assert_no_secrets_in_output "$RUN_OUTPUT"
assert_ok "$RUN_OUTPUT" "research run"
RUN_ID="$(json_field "$RUN_OUTPUT" run_id)"
RUN_ARTIFACT_PATH="$(json_field "$RUN_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$RUN_ARTIFACT_PATH" "research artifact"

# 2. Research list
printf '\n--- Research list ---\n'
LIST_OUTPUT="$(atlas research list --json)"
assert_no_absolute_paths "$LIST_OUTPUT"
assert_no_secrets_in_output "$LIST_OUTPUT"
assert_ok "$LIST_OUTPUT" "research list"
LIST_HAS_RUNID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
items=data.get('items',[])
print(any(i.get('run_id')=='$RUN_ID' for i in items))
" <<<"$LIST_OUTPUT" )"
if [ "$LIST_HAS_RUNID" != "True" ]; then
  printf 'FAIL: research list does not contain run_id %s\n' "$RUN_ID" >&2
  exit 1
fi

# 3. Research show
printf '\n--- Research show ---\n'
SHOW_OUTPUT="$(atlas research show "$RUN_ID" --json)"
assert_no_absolute_paths "$SHOW_OUTPUT"
assert_no_secrets_in_output "$SHOW_OUTPUT"
assert_ok "$SHOW_OUTPUT" "research show"
SHOW_RUN_ID="$(json_field "$SHOW_OUTPUT" artifact.run_id)"
if [ "$SHOW_RUN_ID" != "$RUN_ID" ]; then
  printf 'FAIL: research show returned unexpected run_id\n' >&2
  exit 1
fi

# 4. Research plan
printf '\n--- Research plan ---\n'
PLAN_OUTPUT="$(atlas research plan "$RUN_ID" --json)"
assert_no_absolute_paths "$PLAN_OUTPUT"
assert_no_secrets_in_output "$PLAN_OUTPUT"
assert_ok "$PLAN_OUTPUT" "research plan"
PLAN_ID="$(json_field "$PLAN_OUTPUT" plan_id)"
PLAN_ARTIFACT_PATH="$(json_field "$PLAN_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$PLAN_ARTIFACT_PATH" "plan artifact"

# 5. Research verify
printf '\n--- Research verify ---\n'
VERIFY_OUTPUT="$(atlas research verify "$PLAN_ID" --json)"
assert_no_absolute_paths "$VERIFY_OUTPUT"
assert_no_secrets_in_output "$VERIFY_OUTPUT"
assert_ok "$VERIFY_OUTPUT" "research verify"
VERIFY_ID="$(json_field "$VERIFY_OUTPUT" verification_id)"
VERIFY_RECOMMENDATION="$(json_field "$VERIFY_OUTPUT" recommendation)"
VERIFY_ARTIFACT_PATH="$(json_field "$VERIFY_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$VERIFY_ARTIFACT_PATH" "verification artifact"
if [ "$VERIFY_RECOMMENDATION" != "paper_review_ready" ] && [ "$VERIFY_RECOMMENDATION" != "manual_review_required" ]; then
  printf 'FAIL: unexpected recommendation: %s\n' "$VERIFY_RECOMMENDATION" >&2
  exit 1
fi

# 6. Research evaluate
printf '\n--- Research evaluate ---\n'
EVAL_OUTPUT="$(atlas research evaluate "$PLAN_ID" --data "$WORKSPACE/data/ohlcv.csv" --json)"
assert_no_absolute_paths "$EVAL_OUTPUT"
assert_no_secrets_in_output "$EVAL_OUTPUT"
assert_ok "$EVAL_OUTPUT" "research evaluate"
EVAL_ID="$(json_field "$EVAL_OUTPUT" evaluation_id)"
EVAL_RECOMMENDATION="$(json_field "$EVAL_OUTPUT" recommendation)"
EVAL_ARTIFACT_PATH="$(json_field "$EVAL_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$EVAL_ARTIFACT_PATH" "evaluation artifact"
if [ "$EVAL_RECOMMENDATION" != "paper_evaluation_ready" ] && [ "$EVAL_RECOMMENDATION" != "manual_review_required" ]; then
  printf 'FAIL: unexpected evaluation recommendation: %s\n' "$EVAL_RECOMMENDATION" >&2
  exit 1
fi

# 7. Research summary
printf '\n--- Research summary ---\n'
SUMMARY_OUTPUT="$(atlas research summary --json)"
assert_no_absolute_paths "$SUMMARY_OUTPUT"
assert_no_secrets_in_output "$SUMMARY_OUTPUT"
assert_ok "$SUMMARY_OUTPUT" "research summary"
SUMMARY_HAS_SYMBOL="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
symbols=[s.get('symbol') for s in data.get('symbols',[])]
print('$DEMO_SYMBOL' in symbols)
" <<<"$SUMMARY_OUTPUT" )"
if [ "$SUMMARY_HAS_SYMBOL" != "True" ]; then
  printf 'FAIL: research summary does not include %s\n' "$DEMO_SYMBOL" >&2
  exit 1
fi
SUMMARY_RESEARCH_COUNT="$(json_field "$SUMMARY_OUTPUT" research_count)"
SUMMARY_PLAN_COUNT="$(json_field "$SUMMARY_OUTPUT" plan_count)"
if [ "$SUMMARY_RESEARCH_COUNT" -lt 1 ] || [ "$SUMMARY_PLAN_COUNT" -lt 1 ]; then
  printf 'FAIL: research summary counts too low (research=%s plan=%s)\n' "$SUMMARY_RESEARCH_COUNT" "$SUMMARY_PLAN_COUNT" >&2
  exit 1
fi

# 8. Research check-artifacts
printf '\n--- Research check-artifacts ---\n'
CHECK_OUTPUT="$(atlas research check-artifacts --json)"
assert_no_absolute_paths "$CHECK_OUTPUT"
assert_no_secrets_in_output "$CHECK_OUTPUT"
assert_ok "$CHECK_OUTPUT" "research check-artifacts"
CHECK_STATUS="$(json_field "$CHECK_OUTPUT" status)"
if [ "$CHECK_STATUS" != "research_artifacts_checked" ]; then
  printf 'FAIL: unexpected check-artifacts status: %s\n' "$CHECK_STATUS" >&2
  exit 1
fi
CHECK_RESEARCH_COUNT="$(json_field "$CHECK_OUTPUT" counts.research)"
CHECK_PLAN_COUNT="$(json_field "$CHECK_OUTPUT" counts.plans)"
CHECK_VERIFY_COUNT="$(json_field "$CHECK_OUTPUT" counts.verifications)"
CHECK_EVAL_COUNT="$(json_field "$CHECK_OUTPUT" counts.evaluations)"
if [ "$CHECK_RESEARCH_COUNT" -lt 1 ] || [ "$CHECK_PLAN_COUNT" -lt 1 ]; then
  printf 'FAIL: check-artifacts counts too low (research=%s plans=%s)\n' "$CHECK_RESEARCH_COUNT" "$CHECK_PLAN_COUNT" >&2
  exit 1
fi
if [ "$CHECK_VERIFY_COUNT" -lt 1 ] || [ "$CHECK_EVAL_COUNT" -lt 1 ]; then
  printf 'FAIL: check-artifacts verification/evaluation counts too low (verifications=%s evaluations=%s)\n' "$CHECK_VERIFY_COUNT" "$CHECK_EVAL_COUNT" >&2
  exit 1
fi
CHECK_ISSUES_LEN="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
print(len(data.get('issues',[])))
" <<<"$CHECK_OUTPUT" )"
CHECK_WARNINGS_LEN="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
print(len(data.get('warnings',[])))
" <<<"$CHECK_OUTPUT" )"
if [ -z "$CHECK_ISSUES_LEN" ] || [ -z "$CHECK_WARNINGS_LEN" ]; then
  printf 'FAIL: check-artifacts issues or warnings array missing\n' >&2
  exit 1
fi
assert_no_pending_orders

# 9. Safety checks
printf '\n--- Safety checks ---\n'
assert_no_pending_orders
assert_no_secrets_in_output "$RUN_OUTPUT$LIST_OUTPUT$SHOW_OUTPUT$PLAN_OUTPUT$VERIFY_OUTPUT$EVAL_OUTPUT$SUMMARY_OUTPUT$CHECK_OUTPUT"

printf '\nResearch workflow demo complete.\n'
