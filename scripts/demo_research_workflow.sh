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
  if grep -qiE 'Authorization:|Bearer |sk-[a-zA-Z0-9]{10,}|pplx-[a-zA-Z0-9]{10,}' <<<"$text"; then
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

# 12. Research simulate-provider
printf '\n--- Research simulate-provider ---\n'
SIM_OUTPUT="$(atlas research simulate-provider "$PROMPT_PACKET_ID" --json)"
assert_no_absolute_paths "$SIM_OUTPUT"
assert_no_secrets_in_output "$SIM_OUTPUT"
assert_no_forbidden_fragments "$SIM_OUTPUT" "simulate-provider CLI output"
assert_ok "$SIM_OUTPUT" "research simulate-provider"
SIM_STATUS="$(json_field "$SIM_OUTPUT" status)"
if [ "$SIM_STATUS" != "research_provider_response_created" ]; then
  printf 'FAIL: unexpected simulate-provider status: %s\n' "$SIM_STATUS" >&2
  exit 1
fi
SIM_PROVIDER="$(json_field "$SIM_OUTPUT" provider)"
if [ "$SIM_PROVIDER" != "deterministic-mock" ]; then
  printf 'FAIL: unexpected provider: %s\n' "$SIM_PROVIDER" >&2
  exit 1
fi
SIM_RECOMMENDATION="$(json_field "$SIM_OUTPUT" recommendation)"
if [ "$SIM_RECOMMENDATION" != "provider_response_review_ready" ] && [ "$SIM_RECOMMENDATION" != "manual_review_required" ]; then
  printf 'FAIL: unexpected recommendation: %s\n' "$SIM_RECOMMENDATION" >&2
  exit 1
fi
SIM_RESPONSE_ID="$(json_field "$SIM_OUTPUT" provider_response_id)"
if [ -z "$SIM_RESPONSE_ID" ]; then
  printf 'FAIL: provider_response_id is empty\n' >&2
  exit 1
fi
SIM_ARTIFACT_PATH="$(json_field "$SIM_OUTPUT" artifact_path)"
assert_file_exists "$WORKSPACE/$SIM_ARTIFACT_PATH" "provider response artifact"
assert_no_forbidden_fragments "$(cat "$WORKSPACE/$SIM_ARTIFACT_PATH")" "provider response artifact"
assert_no_pending_orders

# 13. Research timeline after simulate-provider (validate lineage)
printf '\n--- Research timeline (post simulate-provider) ---\n'
TIMELINE_OUTPUT2="$(atlas research timeline --json)"
assert_no_absolute_paths "$TIMELINE_OUTPUT2"
assert_no_secrets_in_output "$TIMELINE_OUTPUT2"
assert_no_forbidden_fragments "$TIMELINE_OUTPUT2" "timeline CLI output after simulate-provider"
assert_ok "$TIMELINE_OUTPUT2" "research timeline after simulate-provider"
TIMELINE_STATUS2="$(json_field "$TIMELINE_OUTPUT2" status)"
if [ "$TIMELINE_STATUS2" != "research_timeline" ]; then
  printf 'FAIL: unexpected timeline status after simulate-provider: %s\n' "$TIMELINE_STATUS2" >&2
  exit 1
fi
TIMELINE_LINEAGE_VALID="$( "$PYTHON_BIN" -c "
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
        if '$SIM_RESPONSE_ID' in prs:
            print('valid')
            break
    break
else:
    print('invalid')
" <<<"$TIMELINE_OUTPUT2" )"
if [ "$TIMELINE_LINEAGE_VALID" != "valid" ]; then
  printf 'FAIL: timeline does not link run_id %s -> prompt %s -> provider response %s\n' "$RUN_ID" "$PROMPT_PACKET_ID" "$SIM_RESPONSE_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 14. Research review-response
printf '\n--- Research review-response ---\n'
REVIEW_OUTPUT="$(atlas research review-response "$SIM_RESPONSE_ID" --json)"
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

# 15. Research timeline after review-response (validate full lineage)
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
            if pr.get('provider_response_id')!='$SIM_RESPONSE_ID':
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
  printf 'FAIL: timeline does not link run_id %s -> prompt %s -> provider response %s -> response review %s\n' "$RUN_ID" "$PROMPT_PACKET_ID" "$SIM_RESPONSE_ID" "$REVIEW_ID" >&2
  exit 1
fi
assert_no_pending_orders

# 16. Research dossier
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

# 17. Research timeline after dossier (validate dossier lineage)
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

# 18. Safety checks
printf '\n--- Safety checks ---\n'
assert_no_pending_orders
assert_no_secrets_in_output "$RUN_OUTPUT$LIST_OUTPUT$SHOW_OUTPUT$PLAN_OUTPUT$VERIFY_OUTPUT$EVAL_OUTPUT$SUMMARY_OUTPUT$CHECK_OUTPUT$TIMELINE_OUTPUT$PROVIDERS_OUTPUT$PROMPT_OUTPUT$SIM_OUTPUT$TIMELINE_OUTPUT2$REVIEW_OUTPUT$TIMELINE_OUTPUT3$DOSSIER_OUTPUT$TIMELINE_OUTPUT4"
assert_no_forbidden_fragments "$RUN_OUTPUT$LIST_OUTPUT$SHOW_OUTPUT$PLAN_OUTPUT$VERIFY_OUTPUT$EVAL_OUTPUT$SUMMARY_OUTPUT$CHECK_OUTPUT$TIMELINE_OUTPUT$PROVIDERS_OUTPUT$PROMPT_OUTPUT$SIM_OUTPUT$TIMELINE_OUTPUT2$REVIEW_OUTPUT$TIMELINE_OUTPUT3$DOSSIER_OUTPUT$TIMELINE_OUTPUT4" "aggregated outputs"

printf '\nResearch workflow demo complete.\n'
