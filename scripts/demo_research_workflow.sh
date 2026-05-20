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
    printf 'Workspace retained.\n'
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
  local cmd="$*"
  if [ -n "${WORKSPACE:-}" ]; then
    cmd="${cmd//$WORKSPACE/<workspace>}"
  fi
  if [ -n "${TMPDIR:-}" ]; then
    cmd="${cmd//$TMPDIR/<tmpdir>}"
  fi
  printf '\n$ atlas %s\n' "$cmd"
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
    printf 'FAIL: %s file not found.\n' "$label" >&2
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
  if grep -qiE '\bAuthorization:\b|\bBearer\b|sk-[a-zA-Z0-9]{10,}|pplx-[a-zA-Z0-9]{10,}' <<<"$text"; then
    printf 'FAIL: Output may contain secret-like content.\n' >&2
    exit 1
  fi
}

assert_no_forbidden_fragments() {
  local text="$1"
  local label="$2"
  local fragments=("Authorization" "Bearer" "APCA" "SECRET" "TOKEN" "PASSWORD" "API_KEY" "sk-" "/Users/" "/private/var/" "broker.example.com")
  for frag in "${fragments[@]}"; do
    if grep -qF "$frag" <<<"$text"; then
      printf 'FAIL: %s contains forbidden fragment: %s\n' "$label" "$frag" >&2
      exit 1
    fi
  done
}

printf 'Atlas Agent research workflow demo\n'
printf 'Symbol: %s\n' "$DEMO_SYMBOL"
printf 'This demo is paper-only and does not require broker credentials.\n'

cd "$REPO_ROOT"
printf '\n$ atlas init <workspace> --template routine-trader\n'
atlas init "$WORKSPACE" --template routine-trader >/dev/null
printf 'Atlas Agent workspace created.\n'

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

# 9. Research timeline
printf '\n--- Research timeline ---\n'
TIMELINE_OUTPUT="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT"
assert_no_secrets_in_output "$TIMELINE_OUTPUT"
assert_ok "$TIMELINE_OUTPUT" "research timeline"
TIMELINE_STATUS="$(json_field "$TIMELINE_OUTPUT" status)"
if [ "$TIMELINE_STATUS" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status: %s\n' "$TIMELINE_STATUS" >&2
  exit 1
fi
TIMELINE_ENTRIES_LEN="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
print(len(data.get('entries',[])))
" <<<"$TIMELINE_OUTPUT" )"
if [ "$TIMELINE_ENTRIES_LEN" -lt 1 ]; then
  printf 'FAIL: timeline entries too low: %s\n' "$TIMELINE_ENTRIES_LEN" >&2
  exit 1
fi
TIMELINE_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID' or e.get('symbol')!='$DEMO_SYMBOL':
        continue
    plans=e.get('plans',[])
    for p in plans:
        if p.get('plan_id')!='$PLAN_ID':
            continue
        vids=[v.get('verification_id') for v in p.get('verifications',[])]
        eids=[ev.get('evaluation_id') for ev in p.get('evaluations',[])]
        if '$VERIFY_ID' in vids and '$EVAL_ID' in eids:
            print('valid')
            break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT" )"
if [ "$TIMELINE_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> plan %s -> verification %s and evaluation %s\n' "$RUN_ID" "$PLAN_ID" "$VERIFY_ID" "$EVAL_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 10. Research providers
printf '\n--- Research providers ---\n'
PROVIDERS_OUTPUT="$(atlas research providers --json)"
assert_no_absolute_paths "$PROVIDERS_OUTPUT"
assert_no_secrets_in_output "$PROVIDERS_OUTPUT"
assert_ok "$PROVIDERS_OUTPUT" "research providers"
PROVIDERS_STATUS="$(json_field "$PROVIDERS_OUTPUT" status)"
if [ "$PROVIDERS_STATUS" != "research_providers_listed" ]; then
  printf 'FAIL: unexpected providers status: %s\n' "$PROVIDERS_STATUS" >&2
  exit 1
fi
PROVIDERS_HAS_DET="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
providers=data.get('providers',[])
for p in providers:
    if p.get('name')=='deterministic' and p.get('enabled')==True and p.get('default')==True and p.get('local')==True and p.get('network')==False and p.get('requires_api_key')==False:
        print('yes')
        break
else:
    print('no')
" <<<"$PROVIDERS_OUTPUT" )"
if [ "$PROVIDERS_HAS_DET" != "yes" ]; then
  printf 'FAIL: Provider discovery missing local deterministic provider.\n' >&2
  exit 1
fi
PROVIDERS_HAS_LLM="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
providers=data.get('providers',[])
for p in providers:
    if p.get('name')=='llm' and p.get('enabled')==False and p.get('default')==False and p.get('network')==False and p.get('requires_api_key')==False:
        print('yes')
        break
else:
    print('no')
" <<<"$PROVIDERS_OUTPUT" )"
if [ "$PROVIDERS_HAS_LLM" != "yes" ]; then
  printf 'FAIL: Provider discovery disabled LLM placeholder is unsafe.\n' >&2
  exit 1
fi
assert_no_pending_orders

# 11. Research prompt
printf '\n--- Research prompt ---\n'
PROMPT_OUTPUT="$(atlas research prompt "$RUN_ID" --json)"
assert_no_absolute_paths "$PROMPT_OUTPUT"
assert_no_secrets_in_output "$PROMPT_OUTPUT"
assert_no_forbidden_fragments "$PROMPT_OUTPUT" "prompt CLI output"
assert_ok "$PROMPT_OUTPUT" "research prompt"
PROMPT_STATUS="$(json_field "$PROMPT_OUTPUT" status)"
if [ "$PROMPT_STATUS" != "research_prompt_packet_created" ]; then
  printf 'FAIL: unexpected prompt status: %s\n' "$PROMPT_STATUS" >&2
  exit 1
fi
PROMPT_PACKET_ID="$(json_field "$PROMPT_OUTPUT" prompt_packet_id)"
if [ -z "$PROMPT_PACKET_ID" ]; then
  printf 'FAIL: prompt_packet_id is empty\n' >&2
  exit 1
fi
PROMPT_ARTIFACT_PATH="$(json_field "$PROMPT_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$PROMPT_ARTIFACT_PATH" "prompt packet artifact"
# Verify artifact has no forbidden fragments
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$PROMPT_ARTIFACT_PATH")" "prompt packet artifact"
assert_no_pending_orders

# 11.5 Research sandbox
printf '\n--- Research sandbox ---\n'
SANDBOX_OUTPUT="$(atlas research sandbox "$PROMPT_PACKET_ID" --json)"
assert_no_absolute_paths "$SANDBOX_OUTPUT"
assert_no_secrets_in_output "$SANDBOX_OUTPUT"
assert_no_forbidden_fragments "$SANDBOX_OUTPUT" "sandbox CLI output"
assert_ok "$SANDBOX_OUTPUT" "research sandbox"
SANDBOX_STATUS="$(json_field "$SANDBOX_OUTPUT" status)"
if [ "$SANDBOX_STATUS" != "research_sandbox_request_created" ]; then
  printf 'FAIL: unexpected sandbox status: %s\n' "$SANDBOX_STATUS" >&2
  exit 1
fi
SANDBOX_ID="$(json_field "$SANDBOX_OUTPUT" sandbox_request_id)"
if [ -z "$SANDBOX_ID" ]; then
  printf 'FAIL: sandbox_request_id is empty\n' >&2
  exit 1
fi
SANDBOX_ARTIFACT_PATH="$(json_field "$SANDBOX_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$SANDBOX_ARTIFACT_PATH" "sandbox request artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$SANDBOX_ARTIFACT_PATH")" "sandbox request artifact"
assert_no_pending_orders

# 12. Research sandbox-list
printf '\n--- Research sandbox-list ---\n'
SANDBOX_LIST_OUTPUT="$(atlas research sandbox-list --json)"
assert_no_absolute_paths "$SANDBOX_LIST_OUTPUT"
assert_no_secrets_in_output "$SANDBOX_LIST_OUTPUT"
assert_no_forbidden_fragments "$SANDBOX_LIST_OUTPUT" "sandbox-list CLI output"
assert_ok "$SANDBOX_LIST_OUTPUT" "research sandbox-list"
SANDBOX_LIST_STATUS="$(json_field "$SANDBOX_LIST_OUTPUT" status)"
if [ "$SANDBOX_LIST_STATUS" != "research_sandbox_listed" ]; then
  printf 'FAIL: unexpected sandbox-list status: %s\n' "$SANDBOX_LIST_STATUS" >&2
  exit 1
fi
SANDBOX_LIST_HAS_ID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
items=data.get('items',[])
print(any(i.get('sandbox_request_id')=='$SANDBOX_ID' for i in items))
" <<<"$SANDBOX_LIST_OUTPUT" )"
if [ "$SANDBOX_LIST_HAS_ID" != "True" ]; then
  printf 'FAIL: sandbox-list does not contain sandbox_request_id %s\n' "$SANDBOX_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 13. Research sandbox-show
printf '\n--- Research sandbox-show ---\n'
SANDBOX_SHOW_OUTPUT="$(atlas research sandbox-show "$SANDBOX_ID" --json)"
assert_no_absolute_paths "$SANDBOX_SHOW_OUTPUT"
assert_no_secrets_in_output "$SANDBOX_SHOW_OUTPUT"
assert_no_forbidden_fragments "$SANDBOX_SHOW_OUTPUT" "sandbox-show CLI output"
assert_ok "$SANDBOX_SHOW_OUTPUT" "research sandbox-show"
SANDBOX_SHOW_STATUS="$(json_field "$SANDBOX_SHOW_OUTPUT" status)"
if [ "$SANDBOX_SHOW_STATUS" != "research_sandbox_loaded" ]; then
  printf 'FAIL: unexpected sandbox-show status: %s\n' "$SANDBOX_SHOW_STATUS" >&2
  exit 1
fi
SANDBOX_SHOW_ID="$(json_field "$SANDBOX_SHOW_OUTPUT" artifact.sandbox_request_id)"
if [ "$SANDBOX_SHOW_ID" != "$SANDBOX_ID" ]; then
  printf 'FAIL: sandbox-show returned unexpected sandbox_request_id\n' >&2
  exit 1
fi
assert_no_pending_orders

# 14. Research sandbox-validate
printf '\n--- Research sandbox-validate ---\n'
SANDBOX_VALIDATE_OUTPUT="$(atlas research sandbox-validate "$SANDBOX_ID" --json)"
assert_no_absolute_paths "$SANDBOX_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$SANDBOX_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$SANDBOX_VALIDATE_OUTPUT" "sandbox-validate CLI output"
assert_ok "$SANDBOX_VALIDATE_OUTPUT" "research sandbox-validate"
SANDBOX_VALIDATE_STATUS="$(json_field "$SANDBOX_VALIDATE_OUTPUT" status)"
if [ "$SANDBOX_VALIDATE_STATUS" != "research_sandbox_validated" ]; then
  printf 'FAIL: unexpected sandbox-validate status: %s\n' "$SANDBOX_VALIDATE_STATUS" >&2
  exit 1
fi
SANDBOX_VALID="$(json_field "$SANDBOX_VALIDATE_OUTPUT" valid)"
if [ "$SANDBOX_VALID" != "True" ]; then
  printf 'FAIL: sandbox-validate returned valid=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 15. Research sandbox-replay
printf '\n--- Research sandbox-replay ---\n'
SANDBOX_REPLAY_OUTPUT="$(atlas research sandbox-replay "$SANDBOX_ID" --json)"
assert_no_absolute_paths "$SANDBOX_REPLAY_OUTPUT"
assert_no_secrets_in_output "$SANDBOX_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$SANDBOX_REPLAY_OUTPUT" "sandbox-replay CLI output"
assert_ok "$SANDBOX_REPLAY_OUTPUT" "research sandbox-replay"
SANDBOX_REPLAY_STATUS="$(json_field "$SANDBOX_REPLAY_OUTPUT" status)"
if [ "$SANDBOX_REPLAY_STATUS" != "research_sandbox_replayed" ]; then
  printf 'FAIL: unexpected sandbox-replay status: %s\n' "$SANDBOX_REPLAY_STATUS" >&2
  exit 1
fi
SANDBOX_REPLAY_MATCH="$(json_field "$SANDBOX_REPLAY_OUTPUT" match)"
if [ "$SANDBOX_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: sandbox-replay returned match=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 16. Provider targets
printf '\n--- Research provider-targets ---\n'
TARGETS_OUTPUT="$(atlas research provider-targets --json)"
assert_no_absolute_paths "$TARGETS_OUTPUT"
assert_no_secrets_in_output "$TARGETS_OUTPUT"
assert_no_forbidden_fragments "$TARGETS_OUTPUT" "provider-targets CLI output"
assert_ok "$TARGETS_OUTPUT" "research provider-targets"
TARGETS_STATUS="$(json_field "$TARGETS_OUTPUT" status)"
if [ "$TARGETS_STATUS" != "research_provider_targets_listed" ]; then
  printf 'FAIL: unexpected provider-targets status: %s\n' "$TARGETS_STATUS" >&2
  exit 1
fi
TARGETS_HAS_DISABLED="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
targets=data.get('targets',[])
for t in targets:
    if t.get('provider_id')=='custom-openai-compatible' and t.get('enabled')==False and t.get('network')==False:
        print('yes')
        break
else:
    print('no')
" <<<"$TARGETS_OUTPUT" )"
if [ "$TARGETS_HAS_DISABLED" != "yes" ]; then
  printf 'FAIL: provider-targets missing disabled custom-openai-compatible target.\n' >&2
  exit 1
fi
assert_no_pending_orders

# 17. Provider plan
printf '\n--- Research provider-plan ---\n'
PLAN_PCP_OUTPUT="$(atlas research provider-plan "$SANDBOX_ID" --provider custom-openai-compatible --model gpt-4o --json)"
assert_no_absolute_paths "$PLAN_PCP_OUTPUT"
assert_no_secrets_in_output "$PLAN_PCP_OUTPUT"
assert_no_forbidden_fragments "$PLAN_PCP_OUTPUT" "provider-plan CLI output"
assert_ok "$PLAN_PCP_OUTPUT" "research provider-plan"
PLAN_PCP_STATUS="$(json_field "$PLAN_PCP_OUTPUT" status)"
if [ "$PLAN_PCP_STATUS" != "research_provider_call_plan_created" ]; then
  printf 'FAIL: unexpected provider-plan status: %s\n' "$PLAN_PCP_STATUS" >&2
  exit 1
fi
PLAN_PCP_ID="$(json_field "$PLAN_PCP_OUTPUT" provider_call_plan_id)"
if [ -z "$PLAN_PCP_ID" ]; then
  printf 'FAIL: provider_call_plan_id is empty\n' >&2
  exit 1
fi
PLAN_PCP_ARTIFACT_PATH="$(json_field "$PLAN_PCP_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$PLAN_PCP_ARTIFACT_PATH" "provider call plan artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$PLAN_PCP_ARTIFACT_PATH")" "provider call plan artifact"
assert_no_pending_orders

# 18. Provider plan list
printf '\n--- Research provider-plan-list ---\n'
PLAN_LIST_PCP_OUTPUT="$(atlas research provider-plan-list --json)"
assert_no_absolute_paths "$PLAN_LIST_PCP_OUTPUT"
assert_no_secrets_in_output "$PLAN_LIST_PCP_OUTPUT"
assert_no_forbidden_fragments "$PLAN_LIST_PCP_OUTPUT" "provider-plan-list CLI output"
assert_ok "$PLAN_LIST_PCP_OUTPUT" "research provider-plan-list"
PLAN_LIST_PCP_STATUS="$(json_field "$PLAN_LIST_PCP_OUTPUT" status)"
if [ "$PLAN_LIST_PCP_STATUS" != "research_provider_call_plans_listed" ]; then
  printf 'FAIL: unexpected provider-plan-list status: %s\n' "$PLAN_LIST_PCP_STATUS" >&2
  exit 1
fi
PLAN_LIST_HAS_ID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
items=data.get('items',[])
print(any(i.get('provider_call_plan_id')=='$PLAN_PCP_ID' for i in items))
" <<<"$PLAN_LIST_PCP_OUTPUT" )"
if [ "$PLAN_LIST_HAS_ID" != "True" ]; then
  printf 'FAIL: provider-plan-list does not contain provider_call_plan_id %s\n' "$PLAN_PCP_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 19. Provider plan show
printf '\n--- Research provider-plan-show ---\n'
PLAN_SHOW_PCP_OUTPUT="$(atlas research provider-plan-show "$PLAN_PCP_ID" --json)"
assert_no_absolute_paths "$PLAN_SHOW_PCP_OUTPUT"
assert_no_secrets_in_output "$PLAN_SHOW_PCP_OUTPUT"
assert_no_forbidden_fragments "$PLAN_SHOW_PCP_OUTPUT" "provider-plan-show CLI output"
assert_ok "$PLAN_SHOW_PCP_OUTPUT" "research provider-plan-show"
PLAN_SHOW_PCP_STATUS="$(json_field "$PLAN_SHOW_PCP_OUTPUT" status)"
if [ "$PLAN_SHOW_PCP_STATUS" != "research_provider_call_plan_loaded" ]; then
  printf 'FAIL: unexpected provider-plan-show status: %s\n' "$PLAN_SHOW_PCP_STATUS" >&2
  exit 1
fi
PLAN_SHOW_PCP_ID="$(json_field "$PLAN_SHOW_PCP_OUTPUT" artifact.provider_call_plan_id)"
if [ "$PLAN_SHOW_PCP_ID" != "$PLAN_PCP_ID" ]; then
  printf 'FAIL: provider-plan-show returned unexpected provider_call_plan_id\n' >&2
  exit 1
fi
assert_no_pending_orders

# 20. Provider plan validate
printf '\n--- Research provider-plan-validate ---\n'
PLAN_VALIDATE_PCP_OUTPUT="$(atlas research provider-plan-validate "$PLAN_PCP_ID" --json)"
assert_no_absolute_paths "$PLAN_VALIDATE_PCP_OUTPUT"
assert_no_secrets_in_output "$PLAN_VALIDATE_PCP_OUTPUT"
assert_no_forbidden_fragments "$PLAN_VALIDATE_PCP_OUTPUT" "provider-plan-validate CLI output"
assert_ok "$PLAN_VALIDATE_PCP_OUTPUT" "research provider-plan-validate"
PLAN_VALIDATE_PCP_STATUS="$(json_field "$PLAN_VALIDATE_PCP_OUTPUT" status)"
if [ "$PLAN_VALIDATE_PCP_STATUS" != "research_provider_call_plan_validated" ]; then
  printf 'FAIL: unexpected provider-plan-validate status: %s\n' "$PLAN_VALIDATE_PCP_STATUS" >&2
  exit 1
fi
PLAN_VALIDATE_PCP_VALID="$(json_field "$PLAN_VALIDATE_PCP_OUTPUT" valid)"
if [ "$PLAN_VALIDATE_PCP_VALID" != "True" ]; then
  printf 'FAIL: provider-plan-validate returned valid=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 21. Provider plan replay
printf '\n--- Research provider-plan-replay ---\n'
PLAN_REPLAY_PCP_OUTPUT="$(atlas research provider-plan-replay "$PLAN_PCP_ID" --json)"
assert_no_absolute_paths "$PLAN_REPLAY_PCP_OUTPUT"
assert_no_secrets_in_output "$PLAN_REPLAY_PCP_OUTPUT"
assert_no_forbidden_fragments "$PLAN_REPLAY_PCP_OUTPUT" "provider-plan-replay CLI output"
assert_ok "$PLAN_REPLAY_PCP_OUTPUT" "research provider-plan-replay"
PLAN_REPLAY_PCP_STATUS="$(json_field "$PLAN_REPLAY_PCP_OUTPUT" status)"
if [ "$PLAN_REPLAY_PCP_STATUS" != "research_provider_call_plan_replayed" ]; then
  printf 'FAIL: unexpected provider-plan-replay status: %s\n' "$PLAN_REPLAY_PCP_STATUS" >&2
  exit 1
fi
PLAN_REPLAY_PCP_MATCH="$(json_field "$PLAN_REPLAY_PCP_OUTPUT" match)"
if [ "$PLAN_REPLAY_PCP_MATCH" != "True" ]; then
  printf 'FAIL: provider-plan-replay returned match=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 22. Provider execution dry-run
printf '\n--- Research provider-execution-dry-run ---\n'
DRY_RUN_OUTPUT="$(atlas research provider-execution-dry-run "$PLAN_PCP_ID" --json)"
assert_no_absolute_paths "$DRY_RUN_OUTPUT"
assert_no_secrets_in_output "$DRY_RUN_OUTPUT"
assert_no_forbidden_fragments "$DRY_RUN_OUTPUT" "provider-execution-dry-run CLI output"
assert_ok "$DRY_RUN_OUTPUT" "research provider-execution-dry-run"
DRY_RUN_STATUS="$(json_field "$DRY_RUN_OUTPUT" status)"
if [ "$DRY_RUN_STATUS" != "research_provider_execution_dry_run_created" ]; then
  printf 'FAIL: unexpected provider-execution-dry-run status: %s\n' "$DRY_RUN_STATUS" >&2
  exit 1
fi
DRY_RUN_ID="$(json_field "$DRY_RUN_OUTPUT" provider_execution_dry_run_id)"
if [ -z "$DRY_RUN_ID" ]; then
  printf 'FAIL: provider_execution_dry_run_id is empty\n' >&2
  exit 1
fi
DRY_RUN_ARTIFACT_PATH="$(json_field "$DRY_RUN_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$DRY_RUN_ARTIFACT_PATH" "provider execution dry-run artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$DRY_RUN_ARTIFACT_PATH")" "provider execution dry-run artifact"
assert_no_pending_orders

# 23. Provider execution list
printf '\n--- Research provider-execution-list ---\n'
DRY_RUN_LIST_OUTPUT="$(atlas research provider-execution-list --json)"
assert_no_absolute_paths "$DRY_RUN_LIST_OUTPUT"
assert_no_secrets_in_output "$DRY_RUN_LIST_OUTPUT"
assert_no_forbidden_fragments "$DRY_RUN_LIST_OUTPUT" "provider-execution-list CLI output"
assert_ok "$DRY_RUN_LIST_OUTPUT" "research provider-execution-list"
DRY_RUN_LIST_STATUS="$(json_field "$DRY_RUN_LIST_OUTPUT" status)"
if [ "$DRY_RUN_LIST_STATUS" != "research_provider_execution_dry_runs_listed" ]; then
  printf 'FAIL: unexpected provider-execution-list status: %s\n' "$DRY_RUN_LIST_STATUS" >&2
  exit 1
fi
DRY_RUN_LIST_HAS_ID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
items=data.get('items',[])
print(any(i.get('provider_execution_dry_run_id')=='$DRY_RUN_ID' for i in items))
" <<<"$DRY_RUN_LIST_OUTPUT" )"
if [ "$DRY_RUN_LIST_HAS_ID" != "True" ]; then
  printf 'FAIL: provider-execution-list does not contain provider_execution_dry_run_id %s\n' "$DRY_RUN_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 24. Provider execution show
printf '\n--- Research provider-execution-show ---\n'
DRY_RUN_SHOW_OUTPUT="$(atlas research provider-execution-show "$DRY_RUN_ID" --json)"
assert_no_absolute_paths "$DRY_RUN_SHOW_OUTPUT"
assert_no_secrets_in_output "$DRY_RUN_SHOW_OUTPUT"
assert_no_forbidden_fragments "$DRY_RUN_SHOW_OUTPUT" "provider-execution-show CLI output"
assert_ok "$DRY_RUN_SHOW_OUTPUT" "research provider-execution-show"
DRY_RUN_SHOW_STATUS="$(json_field "$DRY_RUN_SHOW_OUTPUT" status)"
if [ "$DRY_RUN_SHOW_STATUS" != "research_provider_execution_dry_run_loaded" ]; then
  printf 'FAIL: unexpected provider-execution-show status: %s\n' "$DRY_RUN_SHOW_STATUS" >&2
  exit 1
fi
DRY_RUN_SHOW_ID="$(json_field "$DRY_RUN_SHOW_OUTPUT" artifact.provider_execution_dry_run_id)"
if [ "$DRY_RUN_SHOW_ID" != "$DRY_RUN_ID" ]; then
  printf 'FAIL: provider-execution-show returned unexpected provider_execution_dry_run_id\n' >&2
  exit 1
fi
assert_no_pending_orders

# 25. Provider execution validate
printf '\n--- Research provider-execution-validate ---\n'
DRY_RUN_VALIDATE_OUTPUT="$(atlas research provider-execution-validate "$DRY_RUN_ID" --json)"
assert_no_absolute_paths "$DRY_RUN_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$DRY_RUN_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$DRY_RUN_VALIDATE_OUTPUT" "provider-execution-validate CLI output"
assert_ok "$DRY_RUN_VALIDATE_OUTPUT" "research provider-execution-validate"
DRY_RUN_VALIDATE_STATUS="$(json_field "$DRY_RUN_VALIDATE_OUTPUT" status)"
if [ "$DRY_RUN_VALIDATE_STATUS" != "research_provider_execution_dry_run_validated" ]; then
  printf 'FAIL: unexpected provider-execution-validate status: %s\n' "$DRY_RUN_VALIDATE_STATUS" >&2
  exit 1
fi
DRY_RUN_VALIDATE_VALID="$(json_field "$DRY_RUN_VALIDATE_OUTPUT" valid)"
if [ "$DRY_RUN_VALIDATE_VALID" != "True" ]; then
  printf 'FAIL: provider-execution-validate returned valid=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 26. Provider execution replay
printf '\n--- Research provider-execution-replay ---\n'
DRY_RUN_REPLAY_OUTPUT="$(atlas research provider-execution-replay "$DRY_RUN_ID" --json)"
assert_no_absolute_paths "$DRY_RUN_REPLAY_OUTPUT"
assert_no_secrets_in_output "$DRY_RUN_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$DRY_RUN_REPLAY_OUTPUT" "provider-execution-replay CLI output"
assert_ok "$DRY_RUN_REPLAY_OUTPUT" "research provider-execution-replay"
DRY_RUN_REPLAY_STATUS="$(json_field "$DRY_RUN_REPLAY_OUTPUT" status)"
if [ "$DRY_RUN_REPLAY_STATUS" != "research_provider_execution_dry_run_replayed" ]; then
  printf 'FAIL: unexpected provider-execution-replay status: %s\n' "$DRY_RUN_REPLAY_STATUS" >&2
  exit 1
fi
DRY_RUN_REPLAY_MATCH="$(json_field "$DRY_RUN_REPLAY_OUTPUT" match)"
if [ "$DRY_RUN_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: provider-execution-replay returned match=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 27. Research timeline after provider-execution-dry-run (validate full lineage)
printf '\n--- Research timeline (post provider-execution-dry-run) ---\n'
TIMELINE_OUTPUT_PED="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_PED"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_PED"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_PED" "timeline CLI output after provider-execution-dry-run"
assert_ok "$TIMELINE_OUTPUT_PED" "research timeline after provider-execution-dry-run"
TIMELINE_PED_STATUS="$(json_field "$TIMELINE_OUTPUT_PED" status)"
if [ "$TIMELINE_PED_STATUS" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after provider-execution-dry-run: %s\n' "$TIMELINE_PED_STATUS" >&2
  exit 1
fi
TIMELINE_PED_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                peds=[ped.get('provider_execution_dry_run_id') for ped in pc.get('provider_execution_dry_runs',[])]
                if '$DRY_RUN_ID' in peds:
                    print('valid')
                    break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_PED" )"
if [ "$TIMELINE_PED_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> prompt %s -> sandbox %s -> provider_call_plan %s -> provider_execution_dry_run %s\n' "$RUN_ID" "$PROMPT_PACKET_ID" "$SANDBOX_ID" "$PLAN_PCP_ID" "$DRY_RUN_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 28. Research timeline after provider-plan (validate provider call plan lineage)
printf '\n--- Research timeline (post provider-plan) ---\n'
TIMELINE_OUTPUT_PCP="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_PCP"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_PCP"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_PCP" "timeline CLI output after provider-plan"
assert_ok "$TIMELINE_OUTPUT_PCP" "research timeline after provider-plan"
TIMELINE_PCP_STATUS="$(json_field "$TIMELINE_OUTPUT_PCP" status)"
if [ "$TIMELINE_PCP_STATUS" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after provider-plan: %s\n' "$TIMELINE_PCP_STATUS" >&2
  exit 1
fi
TIMELINE_PCP_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            pcps=[pc.get('provider_call_plan_id') for pc in sr.get('provider_call_plans',[])]
            if '$PLAN_PCP_ID' in pcps:
                print('valid')
                break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_PCP" )"
if [ "$TIMELINE_PCP_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> prompt %s -> sandbox %s -> provider_call_plan %s\n' "$RUN_ID" "$PROMPT_PACKET_ID" "$SANDBOX_ID" "$PLAN_PCP_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 29. Provider execution state (dry_run_only)
printf '\n--- Research provider-execution-state (dry_run_only) ---\n'
STATE_DRY_OUTPUT="$(atlas research provider-execution-state "$DRY_RUN_ID" --to dry_run_only --json)"
assert_no_absolute_paths "$STATE_DRY_OUTPUT"
assert_no_secrets_in_output "$STATE_DRY_OUTPUT"
assert_no_forbidden_fragments "$STATE_DRY_OUTPUT" "provider-execution-state CLI output"
assert_ok "$STATE_DRY_OUTPUT" "research provider-execution-state dry_run_only"
STATE_DRY_STATUS="$(json_field "$STATE_DRY_OUTPUT" status)"
if [ "$STATE_DRY_STATUS" != "research_provider_execution_state_created" ]; then
  printf 'FAIL: unexpected provider-execution-state status: %s\n' "$STATE_DRY_STATUS" >&2
  exit 1
fi
STATE_DRY_ID="$(json_field "$STATE_DRY_OUTPUT" provider_execution_state_id)"
if [ -z "$STATE_DRY_ID" ]; then
  printf 'FAIL: provider_execution_state_id is empty\n' >&2
  exit 1
fi
STATE_DRY_ARTIFACT_PATH="$(json_field "$STATE_DRY_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$STATE_DRY_ARTIFACT_PATH" "provider execution state artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$STATE_DRY_ARTIFACT_PATH")" "provider execution state artifact"
assert_no_pending_orders

# 30. Provider execution state list
printf '\n--- Research provider-execution-state-list ---\n'
STATE_LIST_OUTPUT="$(atlas research provider-execution-state-list --json)"
assert_no_absolute_paths "$STATE_LIST_OUTPUT"
assert_no_secrets_in_output "$STATE_LIST_OUTPUT"
assert_no_forbidden_fragments "$STATE_LIST_OUTPUT" "provider-execution-state-list CLI output"
assert_ok "$STATE_LIST_OUTPUT" "research provider-execution-state-list"
STATE_LIST_STATUS="$(json_field "$STATE_LIST_OUTPUT" status)"
if [ "$STATE_LIST_STATUS" != "research_provider_execution_states_listed" ]; then
  printf 'FAIL: unexpected provider-execution-state-list status: %s\n' "$STATE_LIST_STATUS" >&2
  exit 1
fi
STATE_LIST_HAS_ID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
items=data.get('items',[])
print(any(i.get('provider_execution_state_id')=='$STATE_DRY_ID' for i in items))
" <<<"$STATE_LIST_OUTPUT" )"
if [ "$STATE_LIST_HAS_ID" != "True" ]; then
  printf 'FAIL: provider-execution-state-list does not contain provider_execution_state_id %s\n' "$STATE_DRY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 31. Provider execution state show
printf '\n--- Research provider-execution-state-show ---\n'
STATE_SHOW_OUTPUT="$(atlas research provider-execution-state-show "$STATE_DRY_ID" --json)"
assert_no_absolute_paths "$STATE_SHOW_OUTPUT"
assert_no_secrets_in_output "$STATE_SHOW_OUTPUT"
assert_no_forbidden_fragments "$STATE_SHOW_OUTPUT" "provider-execution-state-show CLI output"
assert_ok "$STATE_SHOW_OUTPUT" "research provider-execution-state-show"
STATE_SHOW_STATUS="$(json_field "$STATE_SHOW_OUTPUT" status)"
if [ "$STATE_SHOW_STATUS" != "research_provider_execution_state_loaded" ]; then
  printf 'FAIL: unexpected provider-execution-state-show status: %s\n' "$STATE_SHOW_STATUS" >&2
  exit 1
fi
STATE_SHOW_ID="$(json_field "$STATE_SHOW_OUTPUT" artifact.provider_execution_state_id)"
if [ "$STATE_SHOW_ID" != "$STATE_DRY_ID" ]; then
  printf 'FAIL: provider-execution-state-show returned unexpected provider_execution_state_id\n' >&2
  exit 1
fi
assert_no_pending_orders

# 32. Provider execution state validate
printf '\n--- Research provider-execution-state-validate ---\n'
STATE_VALIDATE_OUTPUT="$(atlas research provider-execution-state-validate "$STATE_DRY_ID" --json)"
assert_no_absolute_paths "$STATE_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$STATE_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$STATE_VALIDATE_OUTPUT" "provider-execution-state-validate CLI output"
assert_ok "$STATE_VALIDATE_OUTPUT" "research provider-execution-state-validate"
STATE_VALIDATE_STATUS="$(json_field "$STATE_VALIDATE_OUTPUT" status)"
if [ "$STATE_VALIDATE_STATUS" != "research_provider_execution_state_validated" ]; then
  printf 'FAIL: unexpected provider-execution-state-validate status: %s\n' "$STATE_VALIDATE_STATUS" >&2
  exit 1
fi
STATE_VALIDATE_VALID="$(json_field "$STATE_VALIDATE_OUTPUT" valid)"
if [ "$STATE_VALIDATE_VALID" != "True" ]; then
  printf 'FAIL: provider-execution-state-validate returned valid=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 33. Provider execution state replay
printf '\n--- Research provider-execution-state-replay ---\n'
STATE_REPLAY_OUTPUT="$(atlas research provider-execution-state-replay "$STATE_DRY_ID" --json)"
assert_no_absolute_paths "$STATE_REPLAY_OUTPUT"
assert_no_secrets_in_output "$STATE_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$STATE_REPLAY_OUTPUT" "provider-execution-state-replay CLI output"
assert_ok "$STATE_REPLAY_OUTPUT" "research provider-execution-state-replay"
STATE_REPLAY_STATUS="$(json_field "$STATE_REPLAY_OUTPUT" status)"
if [ "$STATE_REPLAY_STATUS" != "research_provider_execution_state_replayed" ]; then
  printf 'FAIL: unexpected provider-execution-state-replay status: %s\n' "$STATE_REPLAY_STATUS" >&2
  exit 1
fi
STATE_REPLAY_MATCH="$(json_field "$STATE_REPLAY_OUTPUT" match)"
if [ "$STATE_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: provider-execution-state-replay returned match=false\n' >&2
  exit 1
fi
assert_no_pending_orders

# 34. Provider execution state manual_unlock_required
printf '\n--- Research provider-execution-state (manual_unlock_required) ---\n'
STATE_MANUAL_OUTPUT="$(atlas research provider-execution-state "$DRY_RUN_ID" --to manual_unlock_required --json)"
assert_no_absolute_paths "$STATE_MANUAL_OUTPUT"
assert_no_secrets_in_output "$STATE_MANUAL_OUTPUT"
assert_no_forbidden_fragments "$STATE_MANUAL_OUTPUT" "provider-execution-state manual_unlock_required CLI output"
assert_ok "$STATE_MANUAL_OUTPUT" "research provider-execution-state manual_unlock_required"
STATE_MANUAL_STATUS="$(json_field "$STATE_MANUAL_OUTPUT" status)"
if [ "$STATE_MANUAL_STATUS" != "research_provider_execution_state_created" ]; then
  printf 'FAIL: unexpected provider-execution-state manual_unlock_required status: %s\n' "$STATE_MANUAL_STATUS" >&2
  exit 1
fi
STATE_MANUAL_ID="$(json_field "$STATE_MANUAL_OUTPUT" provider_execution_state_id)"
assert_no_pending_orders

# 35. Provider execution state provider_call_allowed_but_not_implemented
printf '\n--- Research provider-execution-state (provider_call_allowed_but_not_implemented) ---\n'
STATE_IMPL_OUTPUT="$(atlas research provider-execution-state "$DRY_RUN_ID" --to provider_call_allowed_but_not_implemented --json)"
assert_no_absolute_paths "$STATE_IMPL_OUTPUT"
assert_no_secrets_in_output "$STATE_IMPL_OUTPUT"
assert_no_forbidden_fragments "$STATE_IMPL_OUTPUT" "provider-execution-state provider_call_allowed_but_not_implemented CLI output"
assert_ok "$STATE_IMPL_OUTPUT" "research provider-execution-state provider_call_allowed_but_not_implemented"
STATE_IMPL_STATUS="$(json_field "$STATE_IMPL_OUTPUT" status)"
if [ "$STATE_IMPL_STATUS" != "research_provider_execution_state_created" ]; then
  printf 'FAIL: unexpected provider-execution-state provider_call_allowed_but_not_implemented status: %s\n' "$STATE_IMPL_STATUS" >&2
  exit 1
fi
STATE_IMPL_ID="$(json_field "$STATE_IMPL_OUTPUT" provider_execution_state_id)"
STATE_IMPL_ARTIFACT_PATH="$(json_field "$STATE_IMPL_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$STATE_IMPL_ARTIFACT_PATH" "provider execution state provider_call_allowed_but_not_implemented artifact"
# Verify safety: even this state must NOT allow actual provider calls
STATE_IMPL_ARTIFACT_TEXT="$(cat "$WORKSPACE/$STATE_IMPL_ARTIFACT_PATH")"
if grep -q '"provider_call_allowed": true' <<<"$STATE_IMPL_ARTIFACT_TEXT"; then
  printf 'FAIL: provider_call_allowed_but_not_implemented artifact has provider_call_allowed=true\n' >&2
  exit 1
fi
if grep -q '"actual_provider_call_made": true' <<<"$STATE_IMPL_ARTIFACT_TEXT"; then
  printf 'FAIL: provider_call_allowed_but_not_implemented artifact has actual_provider_call_made=true\n' >&2
  exit 1
fi
assert_no_pending_orders

# 36. Research timeline after state transitions
printf '\n--- Research timeline (post provider-execution-state) ---\n'
TIMELINE_OUTPUT_STATE="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_STATE"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_STATE"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_STATE" "timeline CLI output after provider-execution-state"
assert_ok "$TIMELINE_OUTPUT_STATE" "research timeline after provider-execution-state"
TIMELINE_STATE_STATUS="$(json_field "$TIMELINE_OUTPUT_STATE" status)"
if [ "$TIMELINE_STATE_STATUS" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after provider-execution-state: %s\n' "$TIMELINE_STATE_STATUS" >&2
  exit 1
fi
TIMELINE_STATE_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                for ped in pc.get('provider_execution_dry_runs',[]):
                    if ped.get('provider_execution_dry_run_id')!='$DRY_RUN_ID':
                        continue
                    states=[s.get('provider_execution_state_id') for s in ped.get('provider_execution_states',[])]
                    if '$STATE_DRY_ID' in states and '$STATE_MANUAL_ID' in states and '$STATE_IMPL_ID' in states:
                        print('valid')
                        break
                break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_STATE" )"
if [ "$TIMELINE_STATE_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link state artifacts under dry-run %s\n' "$DRY_RUN_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 37. Research provider execution audit
printf '\n--- Research provider-execution-audit ---\n'
AUDIT_OUTPUT="$(atlas research provider-execution-audit "$STATE_IMPL_ID" --json)"
assert_no_absolute_paths "$AUDIT_OUTPUT"
assert_no_secrets_in_output "$AUDIT_OUTPUT"
assert_no_forbidden_fragments "$AUDIT_OUTPUT" "provider-execution-audit CLI output"
assert_ok "$AUDIT_OUTPUT" "research provider-execution-audit"
AUDIT_STATUS="$(json_field "$AUDIT_OUTPUT" status)"
if [ "$AUDIT_STATUS" != "research_provider_execution_audit_packet_created" ]; then
  printf 'FAIL: unexpected provider-execution-audit status: %s\n' "$AUDIT_STATUS" >&2
  exit 1
fi
AUDIT_PACKET_ID="$(json_field "$AUDIT_OUTPUT" provider_execution_audit_packet_id)"
if [ -z "$AUDIT_PACKET_ID" ]; then
  printf 'FAIL: provider_execution_audit_packet_id is empty after audit\n' >&2
  exit 1
fi
AUDIT_ARTIFACT_PATH="$(json_field "$AUDIT_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$AUDIT_ARTIFACT_PATH" "provider execution audit packet artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$AUDIT_ARTIFACT_PATH")" "provider execution audit packet artifact"
assert_no_pending_orders

# Verify audit packet contains required no-action attestations
AUDIT_ARTIFACT_DATA="$(cat "$WORKSPACE/$AUDIT_ARTIFACT_PATH")"
for field in provider_enabled network_enabled credentials_loaded provider_call_allowed actual_provider_call_made future_provider_execution_possible trading_signal_generated approval_created pending_order_created broker_touched; do
  if ! echo "$AUDIT_ARTIFACT_DATA" | grep -q "\"$field\": false"; then
    printf 'FAIL: audit packet missing or incorrect %s attestation\n' "$field" >&2
    exit 1
  fi
done

# 38. Research provider-execution-audit-list
printf '\n--- Research provider-execution-audit-list ---\n'
AUDIT_LIST_OUTPUT="$(atlas research provider-execution-audit-list --json)"
assert_no_absolute_paths "$AUDIT_LIST_OUTPUT"
assert_no_secrets_in_output "$AUDIT_LIST_OUTPUT"
assert_no_forbidden_fragments "$AUDIT_LIST_OUTPUT" "provider-execution-audit-list CLI output"
assert_ok "$AUDIT_LIST_OUTPUT" "research provider-execution-audit-list"

# 39. Research provider-execution-audit-show
printf '\n--- Research provider-execution-audit-show ---\n'
AUDIT_SHOW_OUTPUT="$(atlas research provider-execution-audit-show "$AUDIT_PACKET_ID" --json)"
assert_no_absolute_paths "$AUDIT_SHOW_OUTPUT"
assert_no_secrets_in_output "$AUDIT_SHOW_OUTPUT"
assert_no_forbidden_fragments "$AUDIT_SHOW_OUTPUT" "provider-execution-audit-show CLI output"
assert_ok "$AUDIT_SHOW_OUTPUT" "research provider-execution-audit-show"
AUDIT_SHOW_ID="$(json_field "$AUDIT_SHOW_OUTPUT" 'artifact.provider_execution_audit_packet_id')"
if [ "$AUDIT_SHOW_ID" != "$AUDIT_PACKET_ID" ]; then
  printf 'FAIL: provider-execution-audit-show returned wrong ID: %s\n' "$AUDIT_SHOW_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 40. Research provider-execution-audit-validate
printf '\n--- Research provider-execution-audit-validate ---\n'
AUDIT_VALIDATE_OUTPUT="$(atlas research provider-execution-audit-validate "$AUDIT_PACKET_ID" --json)"
assert_no_absolute_paths "$AUDIT_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$AUDIT_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$AUDIT_VALIDATE_OUTPUT" "provider-execution-audit-validate CLI output"
assert_ok "$AUDIT_VALIDATE_OUTPUT" "research provider-execution-audit-validate"
AUDIT_VALID="$(json_field "$AUDIT_VALIDATE_OUTPUT" valid)"
if [ "$AUDIT_VALID" != "True" ]; then
  printf 'FAIL: provider-execution-audit-validate returned invalid\n' >&2
  exit 1
fi
assert_no_pending_orders

# 41. Research provider-execution-audit-replay
printf '\n--- Research provider-execution-audit-replay ---\n'
AUDIT_REPLAY_OUTPUT="$(atlas research provider-execution-audit-replay "$AUDIT_PACKET_ID" --json)"
assert_no_absolute_paths "$AUDIT_REPLAY_OUTPUT"
assert_no_secrets_in_output "$AUDIT_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$AUDIT_REPLAY_OUTPUT" "provider-execution-audit-replay CLI output"
assert_ok "$AUDIT_REPLAY_OUTPUT" "research provider-execution-audit-replay"
AUDIT_REPLAY_MATCH="$(json_field "$AUDIT_REPLAY_OUTPUT" match)"
if [ "$AUDIT_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: provider-execution-audit-replay mismatch\n' >&2
  exit 1
fi
assert_no_pending_orders

# 42. Research timeline after audit (validate audit packet lineage)
printf '\n--- Research timeline (post audit) ---\n'
TIMELINE_OUTPUT_AUDIT="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_AUDIT"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_AUDIT"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_AUDIT" "timeline CLI output after audit"
assert_ok "$TIMELINE_OUTPUT_AUDIT" "research timeline after audit"
TIMELINE_AUDIT_STATUS="$(json_field "$TIMELINE_OUTPUT_AUDIT" status)"
if [ "$TIMELINE_AUDIT_STATUS" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after audit: %s\n' "$TIMELINE_AUDIT_STATUS" >&2
  exit 1
fi
TIMELINE_AUDIT_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                for ped in pc.get('provider_execution_dry_runs',[]):
                    if ped.get('provider_execution_dry_run_id')!='$DRY_RUN_ID':
                        continue
                    for s in ped.get('provider_execution_states',[]):
                        if s.get('provider_execution_state_id')!='$STATE_IMPL_ID':
                            continue
                        audits=[a.get('provider_execution_audit_packet_id') for a in s.get('provider_execution_audit_packets',[])]
                        if '$AUDIT_PACKET_ID' in audits:
                            print('valid')
                            break
                    break
                break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_AUDIT" )"
if [ "$TIMELINE_AUDIT_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link audit packet under state %s\n' "$STATE_IMPL_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 43. Research provider-execution-readiness
printf '\n--- Research provider-execution-readiness ---\n'
READINESS_OUTPUT="$(atlas research provider-execution-readiness "$AUDIT_PACKET_ID" --json)"
assert_no_absolute_paths "$READINESS_OUTPUT"
assert_no_secrets_in_output "$READINESS_OUTPUT"
assert_no_forbidden_fragments "$READINESS_OUTPUT" "provider-execution-readiness CLI output"
assert_ok "$READINESS_OUTPUT" "research provider-execution-readiness"
READINESS_STATUS="$(json_field "$READINESS_OUTPUT" readiness_status)"
READINESS_SCORE="$(json_field "$READINESS_OUTPUT" readiness_score)"
READINESS_REPORT_ID="$(json_field "$READINESS_OUTPUT" provider_execution_readiness_report_id)"
READINESS_ARTIFACT_PATH="$(json_field "$READINESS_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$READINESS_ARTIFACT_PATH" "provider execution readiness report artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$READINESS_ARTIFACT_PATH")" "provider execution readiness report artifact"
# Validate key safety fields from artifact
READINESS_ARTIFACT_JSON="$(cat "$WORKSPACE/$READINESS_ARTIFACT_PATH")"
for field in provider_enabled network_enabled credentials_loaded provider_call_allowed actual_provider_call_made trading_signal_generated approval_created pending_order_created broker_touched; do
  value="$(json_bool "$READINESS_ARTIFACT_JSON" "$field")"
  if [ "$value" != "False" ]; then
    printf 'FAIL: readiness report %s is not false\n' "$field" >&2
    exit 1
  fi
done
assert_no_pending_orders

# 44. Research provider-execution-readiness-list
printf '\n--- Research provider-execution-readiness-list ---\n'
READINESS_LIST_OUTPUT="$(atlas research provider-execution-readiness-list --json)"
assert_no_absolute_paths "$READINESS_LIST_OUTPUT"
assert_no_secrets_in_output "$READINESS_LIST_OUTPUT"
assert_no_forbidden_fragments "$READINESS_LIST_OUTPUT" "provider-execution-readiness-list CLI output"
assert_ok "$READINESS_LIST_OUTPUT" "research provider-execution-readiness-list"
READINESS_LISTED="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
items=data.get('items',[])
print(any(i.get('provider_execution_readiness_report_id')=='$READINESS_REPORT_ID' for i in items))
" <<<"$READINESS_LIST_OUTPUT" )"
if [ "$READINESS_LISTED" != "True" ]; then
  printf 'FAIL: readiness report not found in list\n' >&2
  exit 1
fi
assert_no_pending_orders

# 45. Research provider-execution-readiness-show
printf '\n--- Research provider-execution-readiness-show ---\n'
READINESS_SHOW_OUTPUT="$(atlas research provider-execution-readiness-show "$READINESS_REPORT_ID" --json)"
assert_no_absolute_paths "$READINESS_SHOW_OUTPUT"
assert_no_secrets_in_output "$READINESS_SHOW_OUTPUT"
assert_no_forbidden_fragments "$READINESS_SHOW_OUTPUT" "provider-execution-readiness-show CLI output"
assert_ok "$READINESS_SHOW_OUTPUT" "research provider-execution-readiness-show"
READINESS_SHOW_ID="$(json_field "$READINESS_SHOW_OUTPUT" artifact.provider_execution_readiness_report_id)"
if [ "$READINESS_SHOW_ID" != "$READINESS_REPORT_ID" ]; then
  printf 'FAIL: readiness show returned unexpected report id\n' >&2
  exit 1
fi
assert_no_pending_orders

# 46. Research provider-execution-readiness-validate
printf '\n--- Research provider-execution-readiness-validate ---\n'
READINESS_VALIDATE_OUTPUT="$(atlas research provider-execution-readiness-validate "$READINESS_REPORT_ID" --json)"
assert_no_absolute_paths "$READINESS_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$READINESS_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$READINESS_VALIDATE_OUTPUT" "provider-execution-readiness-validate CLI output"
assert_ok "$READINESS_VALIDATE_OUTPUT" "research provider-execution-readiness-validate"
READINESS_VALID="$(json_bool "$READINESS_VALIDATE_OUTPUT" valid)"
if [ "$READINESS_VALID" != "True" ]; then
  printf 'FAIL: readiness validation failed\n' >&2
  exit 1
fi
assert_no_pending_orders

# 47. Research provider-execution-readiness-replay
printf '\n--- Research provider-execution-readiness-replay ---\n'
READINESS_REPLAY_OUTPUT="$(atlas research provider-execution-readiness-replay "$READINESS_REPORT_ID" --json)"
assert_no_absolute_paths "$READINESS_REPLAY_OUTPUT"
assert_no_secrets_in_output "$READINESS_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$READINESS_REPLAY_OUTPUT" "provider-execution-readiness-replay CLI output"
assert_ok "$READINESS_REPLAY_OUTPUT" "research provider-execution-readiness-replay"
READINESS_REPLAY_MATCH="$(json_field "$READINESS_REPLAY_OUTPUT" match)"
if [ "$READINESS_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: readiness replay mismatch\n' >&2
  exit 1
fi
assert_no_pending_orders

# 48. Research provider-execution-chain-doctor
printf '\n--- Research provider-execution-chain-doctor ---\n'
DOCTOR_OUTPUT="$(atlas research provider-execution-chain-doctor "$RUN_ID" --json)"
assert_no_absolute_paths "$DOCTOR_OUTPUT"
assert_no_secrets_in_output "$DOCTOR_OUTPUT"
assert_no_forbidden_fragments "$DOCTOR_OUTPUT" "provider-execution-chain-doctor CLI output"
assert_ok "$DOCTOR_OUTPUT" "research provider-execution-chain-doctor"
DOCTOR_CHAIN_HEALTH="$(json_field "$DOCTOR_OUTPUT" chain_health)"
if [ "$DOCTOR_CHAIN_HEALTH" != "complete" ]; then
  printf 'FAIL: chain doctor reported incomplete chain: %s\n' "$DOCTOR_CHAIN_HEALTH" >&2
  exit 1
fi
DOCTOR_READINESS="$(json_field "$DOCTOR_OUTPUT" readiness_status)"
if [ "$DOCTOR_READINESS" != "chain_review_ready" ]; then
  printf 'FAIL: chain doctor unexpected readiness status: %s\n' "$DOCTOR_READINESS" >&2
  exit 1
fi
assert_no_pending_orders

# 49. Research timeline after readiness (validate readiness report lineage)
printf '\n--- Research timeline (post readiness) ---\n'
TIMELINE_OUTPUT_READINESS="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_READINESS"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_READINESS"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_READINESS" "timeline CLI output after readiness"
assert_ok "$TIMELINE_OUTPUT_READINESS" "research timeline after readiness"
TIMELINE_READINESS_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                for ped in pc.get('provider_execution_dry_runs',[]):
                    if ped.get('provider_execution_dry_run_id')!='$DRY_RUN_ID':
                        continue
                    for s in ped.get('provider_execution_states',[]):
                        if s.get('provider_execution_state_id')!='$STATE_IMPL_ID':
                            continue
                        for a in s.get('provider_execution_audit_packets',[]):
                            if a.get('provider_execution_audit_packet_id')!='$AUDIT_PACKET_ID':
                                continue
                            reports=[r.get('provider_execution_readiness_report_id') for r in a.get('provider_execution_readiness_reports',[])]
                            if '$READINESS_REPORT_ID' in reports:
                                print('valid')
                                break
                        break
                    break
                break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_READINESS" )"
if [ "$TIMELINE_READINESS_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link readiness report under audit packet %s\n' "$AUDIT_PACKET_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 50. Research provider-preflight-freeze
printf '\n--- Research provider-preflight-freeze ---\n'
FREEZE_OUTPUT="$(atlas research provider-preflight-freeze "$READINESS_REPORT_ID" --json)"
assert_no_absolute_paths "$FREEZE_OUTPUT"
assert_no_secrets_in_output "$FREEZE_OUTPUT"
assert_no_forbidden_fragments "$FREEZE_OUTPUT" "provider-preflight-freeze CLI output"
assert_ok "$FREEZE_OUTPUT" "research provider-preflight-freeze"
FREEZE_STATUS="$(json_field "$FREEZE_OUTPUT" status)"
if [ "$FREEZE_STATUS" != "research_provider_preflight_freeze_created" ]; then
  printf 'FAIL: unexpected provider-preflight-freeze status: %s\n' "$FREEZE_STATUS" >&2
  exit 1
fi
FREEZE_ID="$(json_field "$FREEZE_OUTPUT" provider_preflight_freeze_id)"
if [ -z "$FREEZE_ID" ]; then
  printf 'FAIL: provider_preflight_freeze_id is empty after freeze creation\n' >&2
  exit 1
fi
FREEZE_ARTIFACT_PATH="$(json_field "$FREEZE_OUTPUT" artifact_path)"
if [ ! -f "$WORKSPACE/$FREEZE_ARTIFACT_PATH" ]; then
  printf 'FAIL: freeze artifact not found at %s\n' "$WORKSPACE/$FREEZE_ARTIFACT_PATH" >&2
  exit 1
fi
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$FREEZE_ARTIFACT_PATH")" "freeze artifact"
assert_no_pending_orders

# 51. Research provider-preflight-freeze-list
printf '\n--- Research provider-preflight-freeze-list ---\n'
FREEZE_LIST_OUTPUT="$(atlas research provider-preflight-freeze-list --json)"
assert_no_absolute_paths "$FREEZE_LIST_OUTPUT"
assert_no_secrets_in_output "$FREEZE_LIST_OUTPUT"
assert_no_forbidden_fragments "$FREEZE_LIST_OUTPUT" "provider-preflight-freeze-list CLI output"
assert_ok "$FREEZE_LIST_OUTPUT" "research provider-preflight-freeze-list"
FREEZE_LIST_IDS="$( "$PYTHON_BIN" -c "import json,sys; data=json.load(sys.stdin); items=data.get('items',[]); print([i.get('provider_preflight_freeze_id') for i in items])" <<<"$FREEZE_LIST_OUTPUT" )"
if ! printf '%s' "$FREEZE_LIST_IDS" | grep -q "$FREEZE_ID"; then
  printf 'FAIL: freeze %s not found in list output\n' "$FREEZE_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 52. Research provider-preflight-freeze-show
printf '\n--- Research provider-preflight-freeze-show ---\n'
FREEZE_SHOW_OUTPUT="$(atlas research provider-preflight-freeze-show "$FREEZE_ID" --json)"
assert_no_absolute_paths "$FREEZE_SHOW_OUTPUT"
assert_no_secrets_in_output "$FREEZE_SHOW_OUTPUT"
assert_no_forbidden_fragments "$FREEZE_SHOW_OUTPUT" "provider-preflight-freeze-show CLI output"
assert_ok "$FREEZE_SHOW_OUTPUT" "research provider-preflight-freeze-show"
FREEZE_SHOW_ARTIFACT="$( "$PYTHON_BIN" -c "import json,sys; data=json.load(sys.stdin); print(json.dumps(data.get('artifact',{}), indent=2, sort_keys=True))" <<<"$FREEZE_SHOW_OUTPUT" )"
assert_no_forbidden_fragments "$FREEZE_SHOW_ARTIFACT" "freeze show artifact JSON"
FREEZE_SHOW_PROVIDER_CALL_ALLOWED="$(json_field "$FREEZE_SHOW_ARTIFACT" provider_call_allowed)"
if [ "$FREEZE_SHOW_PROVIDER_CALL_ALLOWED" != "False" ]; then
  printf 'FAIL: freeze artifact provider_call_allowed is not False\n' >&2
  exit 1
fi
FREEZE_SHOW_BROKER_TOUCHED="$(json_field "$FREEZE_SHOW_ARTIFACT" broker_touched)"
if [ "$FREEZE_SHOW_BROKER_TOUCHED" != "False" ]; then
  printf 'FAIL: freeze artifact broker_touched is not False\n' >&2
  exit 1
fi
FREEZE_SHOW_TRADING_SIGNAL="$(json_field "$FREEZE_SHOW_ARTIFACT" trading_signal_generated)"
if [ "$FREEZE_SHOW_TRADING_SIGNAL" != "False" ]; then
  printf 'FAIL: freeze artifact trading_signal_generated is not False\n' >&2
  exit 1
fi
assert_no_pending_orders

# 53. Research provider-preflight-freeze-validate
printf '\n--- Research provider-preflight-freeze-validate ---\n'
FREEZE_VALIDATE_OUTPUT="$(atlas research provider-preflight-freeze-validate "$FREEZE_ID" --json)"
assert_no_absolute_paths "$FREEZE_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$FREEZE_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$FREEZE_VALIDATE_OUTPUT" "provider-preflight-freeze-validate CLI output"
assert_ok "$FREEZE_VALIDATE_OUTPUT" "research provider-preflight-freeze-validate"
FREEZE_VALIDATE_VALID="$(json_field "$FREEZE_VALIDATE_OUTPUT" valid)"
if [ "$FREEZE_VALIDATE_VALID" != "True" ]; then
  printf 'FAIL: freeze validation did not report valid=True\n' >&2
  exit 1
fi
assert_no_pending_orders

# 54. Research provider-preflight-freeze-replay
printf '\n--- Research provider-preflight-freeze-replay ---\n'
FREEZE_REPLAY_OUTPUT="$(atlas research provider-preflight-freeze-replay "$FREEZE_ID" --json)"
assert_no_absolute_paths "$FREEZE_REPLAY_OUTPUT"
assert_no_secrets_in_output "$FREEZE_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$FREEZE_REPLAY_OUTPUT" "provider-preflight-freeze-replay CLI output"
assert_ok "$FREEZE_REPLAY_OUTPUT" "research provider-preflight-freeze-replay"
FREEZE_REPLAY_MATCH="$(json_field "$FREEZE_REPLAY_OUTPUT" match)"
if [ "$FREEZE_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: freeze replay did not report match=True\n' >&2
  exit 1
fi
assert_no_pending_orders

# 55. Research provider-preflight-freeze-summary
printf '\n--- Research provider-preflight-freeze-summary ---\n'
FREEZE_SUMMARY_OUTPUT="$(atlas research provider-preflight-freeze-summary "$RUN_ID" --json)"
assert_no_absolute_paths "$FREEZE_SUMMARY_OUTPUT"
assert_no_secrets_in_output "$FREEZE_SUMMARY_OUTPUT"
assert_no_forbidden_fragments "$FREEZE_SUMMARY_OUTPUT" "provider-preflight-freeze-summary CLI output"
assert_ok "$FREEZE_SUMMARY_OUTPUT" "research provider-preflight-freeze-summary"
FREEZE_SUMMARY_EXEC_ALLOWED="$(json_field "$FREEZE_SUMMARY_OUTPUT" provider_execution_allowed)"
if [ "$FREEZE_SUMMARY_EXEC_ALLOWED" != "False" ]; then
  printf 'FAIL: freeze summary provider_execution_allowed is not False\n' >&2
  exit 1
fi
assert_no_pending_orders

# 56. Research timeline after freeze (validate freeze lineage)
printf '\n--- Research timeline (post freeze) ---\n'
TIMELINE_OUTPUT_FREEZE="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_FREEZE"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_FREEZE"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_FREEZE" "timeline CLI output after freeze"
assert_ok "$TIMELINE_OUTPUT_FREEZE" "research timeline after freeze"
TIMELINE_FREEZE_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                for ped in pc.get('provider_execution_dry_runs',[]):
                    if ped.get('provider_execution_dry_run_id')!='$DRY_RUN_ID':
                        continue
                    for s in ped.get('provider_execution_states',[]):
                        if s.get('provider_execution_state_id')!='$STATE_IMPL_ID':
                            continue
                        for a in s.get('provider_execution_audit_packets',[]):
                            if a.get('provider_execution_audit_packet_id')!='$AUDIT_PACKET_ID':
                                continue
                            for r in a.get('provider_execution_readiness_reports',[]):
                                if r.get('provider_execution_readiness_report_id')!='$READINESS_REPORT_ID':
                                    continue
                                freezes=[f.get('provider_preflight_freeze_id') for f in r.get('provider_preflight_freezes',[])]
                                if '$FREEZE_ID' in freezes:
                                    print('valid')
                                    break
                            break
                        break
                    break
                break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_FREEZE" )"
if [ "$TIMELINE_FREEZE_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link freeze under readiness report %s\n' "$READINESS_REPORT_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 57. Research provider-opt-in-policy
printf '\n--- Research provider-opt-in-policy ---\n'
POLICY_OUTPUT="$(atlas research provider-opt-in-policy "$FREEZE_ID" --json)"
assert_no_absolute_paths "$POLICY_OUTPUT"
assert_no_secrets_in_output "$POLICY_OUTPUT"
assert_no_forbidden_fragments "$POLICY_OUTPUT" "provider-opt-in-policy CLI output"
assert_ok "$POLICY_OUTPUT" "research provider-opt-in-policy"
POLICY_STATUS="$(json_field "$POLICY_OUTPUT" status)"
if [ "$POLICY_STATUS" != "research_provider_opt_in_policy_created" ]; then
  printf 'FAIL: unexpected provider-opt-in-policy status: %s\n' "$POLICY_STATUS" >&2
  exit 1
fi
POLICY_ID="$(json_field "$POLICY_OUTPUT" provider_opt_in_policy_id)"
if [ -z "$POLICY_ID" ]; then
  printf 'FAIL: provider_opt_in_policy_id is empty\n' >&2
  exit 1
fi
POLICY_ARTIFACT_PATH="$(json_field "$POLICY_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$POLICY_ARTIFACT_PATH" "provider opt-in policy artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$POLICY_ARTIFACT_PATH")" "provider opt-in policy artifact"
assert_no_pending_orders

# 58. Research provider-opt-in-policy-list
printf '\n--- Research provider-opt-in-policy-list ---\n'
POLICY_LIST_OUTPUT="$(atlas research provider-opt-in-policy-list --json)"
assert_no_absolute_paths "$POLICY_LIST_OUTPUT"
assert_no_secrets_in_output "$POLICY_LIST_OUTPUT"
assert_no_forbidden_fragments "$POLICY_LIST_OUTPUT" "provider-opt-in-policy-list CLI output"
assert_ok "$POLICY_LIST_OUTPUT" "research provider-opt-in-policy-list"
POLICY_LIST_HAS_ITEM="$( "$PYTHON_BIN" -c "import json,sys; d=json.load(sys.stdin); items=d.get('items',[]); print('yes' if any(i.get('provider_opt_in_policy_id')=='$POLICY_ID' for i in items) else 'no')" <<<"$POLICY_LIST_OUTPUT" )"
if [ "$POLICY_LIST_HAS_ITEM" != "yes" ]; then
  printf 'FAIL: policy %s not found in list output\n' "$POLICY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 59. Research provider-opt-in-policy-show
printf '\n--- Research provider-opt-in-policy-show ---\n'
POLICY_SHOW_OUTPUT="$(atlas research provider-opt-in-policy-show "$POLICY_ID" --json)"
assert_no_absolute_paths "$POLICY_SHOW_OUTPUT"
assert_no_secrets_in_output "$POLICY_SHOW_OUTPUT"
assert_no_forbidden_fragments "$POLICY_SHOW_OUTPUT" "provider-opt-in-policy-show CLI output"
assert_ok "$POLICY_SHOW_OUTPUT" "research provider-opt-in-policy-show"
POLICY_SHOW_STATUS="$(json_field "$POLICY_SHOW_OUTPUT" status)"
if [ "$POLICY_SHOW_STATUS" != "research_provider_opt_in_policy_loaded" ]; then
  printf 'FAIL: unexpected provider-opt-in-policy-show status: %s\n' "$POLICY_SHOW_STATUS" >&2
  exit 1
fi
assert_no_pending_orders

# 60. Research provider-opt-in-policy-validate
printf '\n--- Research provider-opt-in-policy-validate ---\n'
POLICY_VALIDATE_OUTPUT="$(atlas research provider-opt-in-policy-validate "$POLICY_ID" --json)"
assert_no_absolute_paths "$POLICY_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$POLICY_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$POLICY_VALIDATE_OUTPUT" "provider-opt-in-policy-validate CLI output"
assert_ok "$POLICY_VALIDATE_OUTPUT" "research provider-opt-in-policy-validate"
POLICY_VALID="$(json_field "$POLICY_VALIDATE_OUTPUT" valid)"
if [ "$POLICY_VALID" != "True" ]; then
  printf 'FAIL: policy validation failed for %s\n' "$POLICY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 61. Research provider-opt-in-policy-replay
printf '\n--- Research provider-opt-in-policy-replay ---\n'
POLICY_REPLAY_OUTPUT="$(atlas research provider-opt-in-policy-replay "$POLICY_ID" --json)"
assert_no_absolute_paths "$POLICY_REPLAY_OUTPUT"
assert_no_secrets_in_output "$POLICY_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$POLICY_REPLAY_OUTPUT" "provider-opt-in-policy-replay CLI output"
assert_ok "$POLICY_REPLAY_OUTPUT" "research provider-opt-in-policy-replay"
POLICY_REPLAY_MATCH="$(json_field "$POLICY_REPLAY_OUTPUT" match)"
if [ "$POLICY_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: policy replay mismatch for %s\n' "$POLICY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 62. Research provider-opt-in-policy-summary
printf '\n--- Research provider-opt-in-policy-summary ---\n'
POLICY_SUMMARY_OUTPUT="$(atlas research provider-opt-in-policy-summary "$RUN_ID" --json)"
assert_no_absolute_paths "$POLICY_SUMMARY_OUTPUT"
assert_no_secrets_in_output "$POLICY_SUMMARY_OUTPUT"
assert_no_forbidden_fragments "$POLICY_SUMMARY_OUTPUT" "provider-opt-in-policy-summary CLI output"
assert_ok "$POLICY_SUMMARY_OUTPUT" "research provider-opt-in-policy-summary"
POLICY_SUMMARY_EXEC_ALLOWED="$(json_field "$POLICY_SUMMARY_OUTPUT" provider_execution_allowed)"
if [ "$POLICY_SUMMARY_EXEC_ALLOWED" != "False" ]; then
  printf 'FAIL: policy summary provider_execution_allowed is not False\n' >&2
  exit 1
fi
assert_no_pending_orders

# 63. Research timeline after policy (validate policy lineage)
printf '\n--- Research timeline (post policy) ---\n'
TIMELINE_OUTPUT_POLICY="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_POLICY"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_POLICY"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_POLICY" "timeline CLI output after policy"
assert_ok "$TIMELINE_OUTPUT_POLICY" "research timeline after policy"
TIMELINE_POLICY_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                for ped in pc.get('provider_execution_dry_runs',[]):
                    if ped.get('provider_execution_dry_run_id')!='$DRY_RUN_ID':
                        continue
                    for s in ped.get('provider_execution_states',[]):
                        if s.get('provider_execution_state_id')!='$STATE_IMPL_ID':
                            continue
                        for a in s.get('provider_execution_audit_packets',[]):
                            if a.get('provider_execution_audit_packet_id')!='$AUDIT_PACKET_ID':
                                continue
                            for r in a.get('provider_execution_readiness_reports',[]):
                                if r.get('provider_execution_readiness_report_id')!='$READINESS_REPORT_ID':
                                    continue
                                for f in r.get('provider_preflight_freezes',[]):
                                    if f.get('provider_preflight_freeze_id')!='$FREEZE_ID':
                                        continue
                                    policies=[p.get('provider_opt_in_policy_id') for p in f.get('provider_opt_in_policies',[])]
                                    if '$POLICY_ID' in policies:
                                        print('valid')
                                        break
                                break
                            break
                        break
                    break
                break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_POLICY" )"
if [ "$TIMELINE_POLICY_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link policy under freeze %s\n' "$FREEZE_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 64. Research provider-credential-boundary
printf '\n--- Research provider-credential-boundary ---\n'
BOUNDARY_OUTPUT="$(atlas research provider-credential-boundary "$POLICY_ID" --json)"
assert_no_absolute_paths "$BOUNDARY_OUTPUT"
assert_no_secrets_in_output "$BOUNDARY_OUTPUT"
assert_no_forbidden_fragments "$BOUNDARY_OUTPUT" "provider-credential-boundary CLI output"
assert_ok "$BOUNDARY_OUTPUT" "research provider-credential-boundary"
BOUNDARY_STATUS="$(json_field "$BOUNDARY_OUTPUT" status)"
if [ "$BOUNDARY_STATUS" != "research_provider_credential_boundary_created" ]; then
  printf 'FAIL: unexpected provider-credential-boundary status: %s\n' "$BOUNDARY_STATUS" >&2
  exit 1
fi
BOUNDARY_ID="$(json_field "$BOUNDARY_OUTPUT" provider_credential_boundary_id)"
if [ -z "$BOUNDARY_ID" ]; then
  printf 'FAIL: provider_credential_boundary_id is empty\n' >&2
  exit 1
fi
BOUNDARY_ARTIFACT_PATH="$(json_field "$BOUNDARY_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$BOUNDARY_ARTIFACT_PATH" "provider credential boundary artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$BOUNDARY_ARTIFACT_PATH")" "provider credential boundary artifact"
assert_no_pending_orders

# 65. Research provider-credential-boundary-list
printf '\n--- Research provider-credential-boundary-list ---\n'
BOUNDARY_LIST_OUTPUT="$(atlas research provider-credential-boundary-list --json)"
assert_no_absolute_paths "$BOUNDARY_LIST_OUTPUT"
assert_no_secrets_in_output "$BOUNDARY_LIST_OUTPUT"
assert_no_forbidden_fragments "$BOUNDARY_LIST_OUTPUT" "provider-credential-boundary-list CLI output"
assert_ok "$BOUNDARY_LIST_OUTPUT" "research provider-credential-boundary-list"
BOUNDARY_LIST_HAS_ITEM="$( "$PYTHON_BIN" -c "import json,sys; d=json.load(sys.stdin); items=d.get('items',[]); print('yes' if any(i.get('provider_credential_boundary_id')=='$BOUNDARY_ID' for i in items) else 'no')" <<<"$BOUNDARY_LIST_OUTPUT" )"
if [ "$BOUNDARY_LIST_HAS_ITEM" != "yes" ]; then
  printf 'FAIL: boundary %s not found in list output\n' "$BOUNDARY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 66. Research provider-credential-boundary-show
printf '\n--- Research provider-credential-boundary-show ---\n'
BOUNDARY_SHOW_OUTPUT="$(atlas research provider-credential-boundary-show "$BOUNDARY_ID" --json)"
assert_no_absolute_paths "$BOUNDARY_SHOW_OUTPUT"
assert_no_secrets_in_output "$BOUNDARY_SHOW_OUTPUT"
assert_no_forbidden_fragments "$BOUNDARY_SHOW_OUTPUT" "provider-credential-boundary-show CLI output"
assert_ok "$BOUNDARY_SHOW_OUTPUT" "research provider-credential-boundary-show"
BOUNDARY_SHOW_STATUS="$(json_field "$BOUNDARY_SHOW_OUTPUT" status)"
if [ "$BOUNDARY_SHOW_STATUS" != "research_provider_credential_boundary_loaded" ]; then
  printf 'FAIL: unexpected provider-credential-boundary-show status: %s\n' "$BOUNDARY_SHOW_STATUS" >&2
  exit 1
fi
assert_no_pending_orders

# 67. Research provider-credential-boundary-validate
printf '\n--- Research provider-credential-boundary-validate ---\n'
BOUNDARY_VALIDATE_OUTPUT="$(atlas research provider-credential-boundary-validate "$BOUNDARY_ID" --json)"
assert_no_absolute_paths "$BOUNDARY_VALIDATE_OUTPUT"
assert_no_secrets_in_output "$BOUNDARY_VALIDATE_OUTPUT"
assert_no_forbidden_fragments "$BOUNDARY_VALIDATE_OUTPUT" "provider-credential-boundary-validate CLI output"
assert_ok "$BOUNDARY_VALIDATE_OUTPUT" "research provider-credential-boundary-validate"
BOUNDARY_VALID="$(json_field "$BOUNDARY_VALIDATE_OUTPUT" valid)"
if [ "$BOUNDARY_VALID" != "True" ]; then
  printf 'FAIL: boundary validation failed for %s\n' "$BOUNDARY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 68. Research provider-credential-boundary-replay
printf '\n--- Research provider-credential-boundary-replay ---\n'
BOUNDARY_REPLAY_OUTPUT="$(atlas research provider-credential-boundary-replay "$BOUNDARY_ID" --json)"
assert_no_absolute_paths "$BOUNDARY_REPLAY_OUTPUT"
assert_no_secrets_in_output "$BOUNDARY_REPLAY_OUTPUT"
assert_no_forbidden_fragments "$BOUNDARY_REPLAY_OUTPUT" "provider-credential-boundary-replay CLI output"
assert_ok "$BOUNDARY_REPLAY_OUTPUT" "research provider-credential-boundary-replay"
BOUNDARY_REPLAY_MATCH="$(json_field "$BOUNDARY_REPLAY_OUTPUT" match)"
if [ "$BOUNDARY_REPLAY_MATCH" != "True" ]; then
  printf 'FAIL: boundary replay mismatch for %s\n' "$BOUNDARY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 69. Research provider-credential-boundary-summary
printf '\n--- Research provider-credential-boundary-summary ---\n'
BOUNDARY_SUMMARY_OUTPUT="$(atlas research provider-credential-boundary-summary "$RUN_ID" --json)"
assert_no_absolute_paths "$BOUNDARY_SUMMARY_OUTPUT"
assert_no_secrets_in_output "$BOUNDARY_SUMMARY_OUTPUT"
assert_no_forbidden_fragments "$BOUNDARY_SUMMARY_OUTPUT" "provider-credential-boundary-summary CLI output"
assert_ok "$BOUNDARY_SUMMARY_OUTPUT" "research provider-credential-boundary-summary"
BOUNDARY_SUMMARY_CREDS_LOADED="$(json_field "$BOUNDARY_SUMMARY_OUTPUT" credentials_loaded)"
if [ "$BOUNDARY_SUMMARY_CREDS_LOADED" != "False" ]; then
  printf 'FAIL: boundary summary credentials_loaded is not False\n' >&2
  exit 1
fi
BOUNDARY_SUMMARY_ENV_READ="$(json_field "$BOUNDARY_SUMMARY_OUTPUT" env_read_attempted)"
if [ "$BOUNDARY_SUMMARY_ENV_READ" != "False" ]; then
  printf 'FAIL: boundary summary env_read_attempted is not False\n' >&2
  exit 1
fi
BOUNDARY_SUMMARY_DOTENV="$(json_field "$BOUNDARY_SUMMARY_OUTPUT" dotenv_loaded)"
if [ "$BOUNDARY_SUMMARY_DOTENV" != "False" ]; then
  printf 'FAIL: boundary summary dotenv_loaded is not False\n' >&2
  exit 1
fi
assert_no_pending_orders

# 70. Research timeline after credential boundary
printf '\n--- Research timeline (post credential boundary) ---\n'
TIMELINE_OUTPUT_BOUNDARY="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_BOUNDARY"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_BOUNDARY"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_BOUNDARY" "timeline CLI output after credential boundary"
assert_ok "$TIMELINE_OUTPUT_BOUNDARY" "research timeline after credential boundary"
TIMELINE_BOUNDARY_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for sr in p.get('sandbox_requests',[]):
            if sr.get('sandbox_request_id')!='$SANDBOX_ID':
                continue
            for pc in sr.get('provider_call_plans',[]):
                if pc.get('provider_call_plan_id')!='$PLAN_PCP_ID':
                    continue
                for ped in pc.get('provider_execution_dry_runs',[]):
                    if ped.get('provider_execution_dry_run_id')!='$DRY_RUN_ID':
                        continue
                    for s in ped.get('provider_execution_states',[]):
                        if s.get('provider_execution_state_id')!='$STATE_IMPL_ID':
                            continue
                        for a in s.get('provider_execution_audit_packets',[]):
                            if a.get('provider_execution_audit_packet_id')!='$AUDIT_PACKET_ID':
                                continue
                            for r in a.get('provider_execution_readiness_reports',[]):
                                if r.get('provider_execution_readiness_report_id')!='$READINESS_REPORT_ID':
                                    continue
                                for f in r.get('provider_preflight_freezes',[]):
                                    if f.get('provider_preflight_freeze_id')!='$FREEZE_ID':
                                        continue
                                    for pol in f.get('provider_opt_in_policies',[]):
                                        if pol.get('provider_opt_in_policy_id')!='$POLICY_ID':
                                            continue
                                        boundaries=[b.get('provider_credential_boundary_id') for b in pol.get('provider_credential_boundaries',[])]
                                        if '$BOUNDARY_ID' in boundaries:
                                            print('valid')
                                            break
                                    break
                                break
                            break
                        break
                    break
                break
            break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_BOUNDARY" )"
if [ "$TIMELINE_BOUNDARY_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link boundary under policy %s\n' "$POLICY_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 71. Create local provider response fixture and import it
printf '\n--- Import provider response ---\n'
IMPORT_FIXTURE="$WORKSPACE/imported_response.json"
printf '%s\n' '{"summary":"External analysis of market context.","sections":[{"title":"Scope","content":"Review local sandbox request only."},{"title":"Risks","content":"No live trading is authorized."}],"safety_checks":[{"name":"paper_only","status":"pass","notes":"Mode is paper."}],"limitations":["Not financial advice.","No real market data queried."]}' > "$IMPORT_FIXTURE"
IMPORT_OUTPUT="$(atlas research import-provider-response "$SANDBOX_ID" --file "$IMPORT_FIXTURE" --json)"
assert_no_absolute_paths "$IMPORT_OUTPUT"
assert_no_secrets_in_output "$IMPORT_OUTPUT"
assert_no_forbidden_fragments "$IMPORT_OUTPUT" "import-provider-response CLI output"
assert_ok "$IMPORT_OUTPUT" "research import-provider-response"
IMPORT_STATUS="$(json_field "$IMPORT_OUTPUT" status)"
if [ "$IMPORT_STATUS" != "research_provider_response_imported" ]; then
  printf 'FAIL: unexpected import-provider-response status: %s\n' "$IMPORT_STATUS" >&2
  exit 1
fi
IMPORT_RESPONSE_ID="$(json_field "$IMPORT_OUTPUT" provider_response_id)"
if [ -z "$IMPORT_RESPONSE_ID" ]; then
  printf 'FAIL: provider_response_id is empty after import\n' >&2
  exit 1
fi
IMPORT_ARTIFACT_PATH="$(json_field "$IMPORT_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$IMPORT_ARTIFACT_PATH" "imported provider response artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$IMPORT_ARTIFACT_PATH")" "imported provider response artifact"
assert_no_pending_orders

# 38. Research timeline after import (validate imported lineage)
printf '\n--- Research timeline (post import) ---\n'
TIMELINE_OUTPUT_IMPORT="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT_IMPORT"
assert_no_secrets_in_output "$TIMELINE_OUTPUT_IMPORT"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT_IMPORT" "timeline CLI output after import"
assert_ok "$TIMELINE_OUTPUT_IMPORT" "research timeline after import"
TIMELINE_IMPORT_STATUS="$(json_field "$TIMELINE_OUTPUT_IMPORT" status)"
if [ "$TIMELINE_IMPORT_STATUS" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after import: %s\n' "$TIMELINE_IMPORT_STATUS" >&2
  exit 1
fi
TIMELINE_IMPORT_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        prs=[pr.get('provider_response_id') for pr in p.get('provider_responses',[])]
        if '$IMPORT_RESPONSE_ID' in prs:
            print('valid')
            break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT_IMPORT" )"
if [ "$TIMELINE_IMPORT_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> prompt %s -> imported provider response %s\n' "$RUN_ID" "$PROMPT_PACKET_ID" "$IMPORT_RESPONSE_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 39. Research review-response on imported response
printf '\n--- Research review-response ---\n'
REVIEW_OUTPUT="$(atlas research review-response "$IMPORT_RESPONSE_ID" --json)"
assert_no_absolute_paths "$REVIEW_OUTPUT"
assert_no_secrets_in_output "$REVIEW_OUTPUT"
assert_no_forbidden_fragments "$REVIEW_OUTPUT" "review-response CLI output"
assert_ok "$REVIEW_OUTPUT" "research review-response"
REVIEW_STATUS="$(json_field "$REVIEW_OUTPUT" status)"
if [ "$REVIEW_STATUS" != "research_response_review_created" ]; then
  printf 'FAIL: unexpected review-response status: %s\n' "$REVIEW_STATUS" >&2
  exit 1
fi
REVIEW_RECOMMENDATION="$(json_field "$REVIEW_OUTPUT" recommendation)"
if [ "$REVIEW_RECOMMENDATION" != "provider_response_review_ready" ] && [ "$REVIEW_RECOMMENDATION" != "manual_review_required" ]; then
  printf 'FAIL: unexpected review-response recommendation: %s\n' "$REVIEW_RECOMMENDATION" >&2
  exit 1
fi
REVIEW_ID="$(json_field "$REVIEW_OUTPUT" response_review_id)"
if [ -z "$REVIEW_ID" ]; then
  printf 'FAIL: response_review_id is empty\n' >&2
  exit 1
fi
REVIEW_ARTIFACT_PATH="$(json_field "$REVIEW_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$REVIEW_ARTIFACT_PATH" "response review artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$REVIEW_ARTIFACT_PATH")" "response review artifact"
assert_no_pending_orders

# 40. Research timeline after review-response (validate full lineage)
printf '\n--- Research timeline (post review-response) ---\n'
TIMELINE_OUTPUT3="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT3"
assert_no_secrets_in_output "$TIMELINE_OUTPUT3"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT3" "timeline CLI output after review-response"
assert_ok "$TIMELINE_OUTPUT3" "research timeline after review-response"
TIMELINE_STATUS3="$(json_field "$TIMELINE_OUTPUT3" status)"
if [ "$TIMELINE_STATUS3" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after review-response: %s\n' "$TIMELINE_STATUS3" >&2
  exit 1
fi
TIMELINE_FULL_LINEAGE_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    prompts=e.get('prompts',[])
    for p in prompts:
        if p.get('prompt_packet_id')!='$PROMPT_PACKET_ID':
            continue
        for pr in p.get('provider_responses',[]):
            if pr.get('provider_response_id')!='$IMPORT_RESPONSE_ID':
                continue
            rrs=[rr.get('response_review_id') for rr in pr.get('response_reviews',[])]
            if '$REVIEW_ID' in rrs:
                print('valid')
                break
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT3" )"
if [ "$TIMELINE_FULL_LINEAGE_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> prompt %s -> provider response %s -> response review %s\n' "$RUN_ID" "$PROMPT_PACKET_ID" "$IMPORT_RESPONSE_ID" "$REVIEW_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 41. Research dossier
printf '\n--- Research dossier ---\n'
DOSSIER_OUTPUT="$(atlas research dossier "$RUN_ID" --json)"
assert_no_absolute_paths "$DOSSIER_OUTPUT"
assert_no_secrets_in_output "$DOSSIER_OUTPUT"
assert_no_forbidden_fragments "$DOSSIER_OUTPUT" "dossier CLI output"
assert_ok "$DOSSIER_OUTPUT" "research dossier"
DOSSIER_STATUS="$(json_field "$DOSSIER_OUTPUT" status)"
if [ "$DOSSIER_STATUS" != "research_dossier_created" ]; then
  printf 'FAIL: unexpected dossier status: %s\n' "$DOSSIER_STATUS" >&2
  exit 1
fi
DOSSIER_ID="$(json_field "$DOSSIER_OUTPUT" dossier_id)"
if [ -z "$DOSSIER_ID" ]; then
  printf 'FAIL: dossier_id is empty\n' >&2
  exit 1
fi
DOSSIER_RECOMMENDATION="$(json_field "$DOSSIER_OUTPUT" recommendation)"
if [ "$DOSSIER_RECOMMENDATION" != "research_dossier_ready" ] && [ "$DOSSIER_RECOMMENDATION" != "manual_review_required" ]; then
  printf 'FAIL: unexpected dossier recommendation: %s\n' "$DOSSIER_RECOMMENDATION" >&2
  exit 1
fi
DOSSIER_ARTIFACT_PATH="$(json_field "$DOSSIER_OUTPUT" artifact_path)"
if [ ! -f "$WORKSPACE/$DOSSIER_ARTIFACT_PATH" ]; then
  printf 'FAIL: dossier artifact not found.\n' >&2
  exit 1
fi
assert_no_pending_orders

# 42. Research timeline after dossier (validate dossier lineage)
printf '\n--- Research timeline (post dossier) ---\n'
TIMELINE_OUTPUT4="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT4"
assert_no_secrets_in_output "$TIMELINE_OUTPUT4"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT4" "timeline CLI output after dossier"
assert_ok "$TIMELINE_OUTPUT4" "research timeline after dossier"
TIMELINE_STATUS4="$(json_field "$TIMELINE_OUTPUT4" status)"
if [ "$TIMELINE_STATUS4" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after dossier: %s\n' "$TIMELINE_STATUS4" >&2
  exit 1
fi
TIMELINE_DOSSIER_VALID="$( "$PYTHON_BIN" -c "
import json,sys
data=json.load(sys.stdin)
entries=data.get('entries',[])
for e in entries:
    if e.get('run_id')!='$RUN_ID':
        continue
    ds=[d.get('dossier_id') for d in e.get('dossiers',[])]
    if '$DOSSIER_ID' in ds:
        print('valid')
        break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT4" )"
if [ "$TIMELINE_DOSSIER_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> dossier %s\n' "$RUN_ID" "$DOSSIER_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 43. Safety checks
printf '\n--- Safety checks ---\n'
assert_no_pending_orders
assert_no_secrets_in_output "$RUN_OUTPUT$LIST_OUTPUT$SHOW_OUTPUT$PLAN_OUTPUT$VERIFY_OUTPUT$EVAL_OUTPUT$SUMMARY_OUTPUT$CHECK_OUTPUT$TIMELINE_OUTPUT$PROVIDERS_OUTPUT$PROMPT_OUTPUT$SANDBOX_OUTPUT$SANDBOX_LIST_OUTPUT$SANDBOX_SHOW_OUTPUT$SANDBOX_VALIDATE_OUTPUT$SANDBOX_REPLAY_OUTPUT$TARGETS_OUTPUT$PLAN_PCP_OUTPUT$PLAN_LIST_PCP_OUTPUT$PLAN_SHOW_PCP_OUTPUT$PLAN_VALIDATE_PCP_OUTPUT$PLAN_REPLAY_PCP_OUTPUT$TIMELINE_OUTPUT_PCP$DRY_RUN_OUTPUT$DRY_RUN_LIST_OUTPUT$DRY_RUN_SHOW_OUTPUT$DRY_RUN_VALIDATE_OUTPUT$DRY_RUN_REPLAY_OUTPUT$TIMELINE_OUTPUT_PED$STATE_DRY_OUTPUT$STATE_LIST_OUTPUT$STATE_SHOW_OUTPUT$STATE_VALIDATE_OUTPUT$STATE_REPLAY_OUTPUT$STATE_MANUAL_OUTPUT$STATE_IMPL_OUTPUT$TIMELINE_OUTPUT_STATE$IMPORT_OUTPUT$TIMELINE_OUTPUT_IMPORT$REVIEW_OUTPUT$TIMELINE_OUTPUT3$DOSSIER_OUTPUT$TIMELINE_OUTPUT4"
assert_no_forbidden_fragments "$RUN_OUTPUT$LIST_OUTPUT$SHOW_OUTPUT$PLAN_OUTPUT$VERIFY_OUTPUT$EVAL_OUTPUT$SUMMARY_OUTPUT$CHECK_OUTPUT$TIMELINE_OUTPUT$PROVIDERS_OUTPUT$PROMPT_OUTPUT$SANDBOX_OUTPUT$SANDBOX_LIST_OUTPUT$SANDBOX_SHOW_OUTPUT$SANDBOX_VALIDATE_OUTPUT$SANDBOX_REPLAY_OUTPUT$TARGETS_OUTPUT$PLAN_PCP_OUTPUT$PLAN_LIST_PCP_OUTPUT$PLAN_SHOW_PCP_OUTPUT$PLAN_VALIDATE_PCP_OUTPUT$PLAN_REPLAY_PCP_OUTPUT$TIMELINE_OUTPUT_PCP$DRY_RUN_OUTPUT$DRY_RUN_LIST_OUTPUT$DRY_RUN_SHOW_OUTPUT$DRY_RUN_VALIDATE_OUTPUT$DRY_RUN_REPLAY_OUTPUT$TIMELINE_OUTPUT_PED$STATE_DRY_OUTPUT$STATE_LIST_OUTPUT$STATE_SHOW_OUTPUT$STATE_VALIDATE_OUTPUT$STATE_REPLAY_OUTPUT$STATE_MANUAL_OUTPUT$STATE_IMPL_OUTPUT$TIMELINE_OUTPUT_STATE$IMPORT_OUTPUT$TIMELINE_OUTPUT_IMPORT$REVIEW_OUTPUT$TIMELINE_OUTPUT3$DOSSIER_OUTPUT$TIMELINE_OUTPUT4" "aggregated outputs"

printf '\nResearch workflow demo complete.\n'
