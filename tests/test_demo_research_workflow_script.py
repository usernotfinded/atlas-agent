from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_research_workflow.sh"


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)


def test_mutation_guard() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "git add",
        "git commit",
        "git push",
        "git tag",
        "git reset",
        "git clean",
        "git restore",
        "git switch",
        "rm -rf .git",
    )
    for phrase in forbidden:
        assert phrase not in text, f"Forbidden mutation phrase: {phrase}"


def test_uses_mktemp_and_cleanup_trap() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "mktemp -d" in text
    assert "trap" in text
    assert "ATLAS_KEEP_RESEARCH_DEMO_DIR" in text or "--keep-workspace" in text


def test_no_jq_dependency() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "jq " not in text
    assert "| jq" not in text


def test_no_forbidden_phrases_in_script() -> None:
    lower = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden = (
        "btc-usd",
        "enable_live_trading = true",
        "atlas run --mode live",
        "--mode live",
        "best broker",
        "recommended broker",
        "guaranteed profit",
        "profit bot",
        "autonomous money",
        "will make money",
        "makes money",
        "production-grade live",
    )
    for phrase in forbidden:
        assert phrase not in lower, f"Forbidden phrase: {phrase}"


@pytest.fixture
def fake_atlas_workspace(tmp_path: Path) -> Path:
    """Create a fake atlas binary and workspace structure."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = tmp_path / "atlas_calls.log"

    # Build fake atlas script using template to avoid f-string escaping issues
    template = '''#!/usr/bin/env python3
import json
import os
import sys

ARGS = sys.argv[1:]
LOG_PATH = "LOG_PATH_PLACEHOLDER"

with open(LOG_PATH, "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {ARGS[2]} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{symbol}/{run_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "run_id": run_id, "symbol": symbol, "mode": "paper",
            "provider": "deterministic", "summary": "s", "thesis": "t",
            "market_context": "m", "risks": [], "invalidation_conditions": [],
            "paper_only_plan": "p", "memory_hits": [], "citations": [],
            "warnings": [], "artifact_path": artifact_path, "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "created", "symbol": symbol, "mode": "paper",
        "provider": "deterministic", "run_id": run_id, "artifact_path": artifact_path,
        "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({
        "ok": True, "status": "research_listed",
        "items": [{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "provider": "deterministic", "warnings_count": 0
        }]
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    run_id = ARGS[2]
    print(json.dumps({
        "ok": True, "status": "research_loaded",
        "artifact": {
            "run_id": run_id, "symbol": "ATLAS-DEMO", "mode": "paper",
            "provider": "deterministic", "summary": "s", "thesis": "t",
            "market_context": "m", "risks": [], "invalidation_conditions": [],
            "paper_only_plan": "p", "memory_hits": [], "citations": [],
            "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "metadata": {}
        }
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    run_id = ARGS[2]
    plan_id = "demoplanid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/plans/{plan_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "plan_id": plan_id, "source_run_id": run_id, "symbol": symbol,
            "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "thesis_recap": "t", "constraints": ["paper-only"],
            "risk_notes": ["r"], "invalidation_checks": ["i"],
            "paper_only_actions": ["a"], "verification_steps": ["v"],
            "warnings": [], "artifact_path": artifact_path, "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "paper_plan_created", "symbol": symbol,
        "source_run_id": run_id, "plan_id": plan_id,
        "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    plan_id = ARGS[2]
    verification_id = "demoverifyid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/verifications/{verification_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "verification_id": verification_id, "source_plan_id": plan_id,
            "source_run_id": "demorunid12345", "symbol": symbol,
            "mode": "paper", "provider": "deterministic",
            "source_plan_path": f".atlas/research/{symbol}/plans/{plan_id}.json",
            "checks": [], "passed_checks": 8, "failed_checks": 0,
            "warnings": [], "recommendation": "paper_review_ready",
            "artifact_path": artifact_path, "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_verification_created", "symbol": symbol,
        "source_plan_id": plan_id, "verification_id": verification_id,
        "recommendation": "paper_review_ready", "passed_checks": 8,
        "failed_checks": 0, "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    plan_id = ARGS[2]
    verification_id = "demoverifyid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/verifications/{verification_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "verification_id": verification_id, "source_plan_id": plan_id,
            "source_run_id": "demorunid12345", "symbol": symbol,
            "mode": "paper", "provider": "deterministic",
            "source_plan_path": f".atlas/research/{symbol}/plans/{plan_id}.json",
            "checks": [], "passed_checks": 8, "failed_checks": 0,
            "warnings": [], "recommendation": "paper_review_ready",
            "artifact_path": artifact_path, "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_verification_created", "symbol": symbol,
        "source_plan_id": plan_id, "verification_id": verification_id,
        "recommendation": "paper_review_ready", "passed_checks": 8,
        "failed_checks": 0, "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    plan_id = ARGS[2]
    evaluation_id = "demoevalid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/evaluations/{evaluation_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "evaluation_id": evaluation_id, "source_plan_id": plan_id,
            "source_run_id": "demorunid12345", "symbol": symbol,
            "mode": "paper", "provider": "deterministic",
            "source_plan_path": f".atlas/research/{symbol}/plans/{plan_id}.json",
            "data_source": "data/ohlcv.csv", "data_summary": {"row_count": 3},
            "checks": [], "metrics": {"row_count": 3, "latest_close": 107},
            "warnings": [], "recommendation": "paper_evaluation_ready",
            "artifact_path": artifact_path, "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_evaluation_created", "symbol": symbol,
        "source_plan_id": plan_id, "evaluation_id": evaluation_id,
        "recommendation": "paper_evaluation_ready", "passed_checks": 9,
        "failed_checks": 0, "artifact_path": artifact_path,
        "metrics": {"row_count": 3, "latest_close": 107}, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({
        "ok": True, "status": "research_summary",
        "research_count": 1, "plan_count": 1,
        "symbols": [{
            "symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1,
            "latest_research_run_id": "demorunid12345",
            "latest_plan_id": "demoplanid12345",
            "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
        }],
        "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({
        "ok": True, "status": "research_artifacts_checked",
        "counts": {"research": 1, "plans": 1, "verifications": 1, "evaluations": 1, "prompts": 1, "provider_responses": 1, "response_reviews": 1, "provider_call_plans": 1},
        "issues": [], "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({
        "ok": True, "status": "research_timeline",
        "entries": [{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{
                "plan_id": "demoplanid12345",
                "created_at": "2026-01-01T00:00:00+00:00",
                "artifact_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json",
                "verifications": [{
                    "verification_id": "demoverifyid12345",
                    "recommendation": "paper_review_ready",
                    "artifact_path": ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
                }],
                "evaluations": [{
                    "evaluation_id": "demoevalid12345",
                    "recommendation": "paper_evaluation_ready",
                    "artifact_path": ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
                }]
            }],
            "prompts": [{
                "prompt_packet_id": "demopromptid12345",
                "created_at": "2026-01-01T00:00:00+00:00",
                "artifact_path": ".atlas/research/ATLAS-DEMO/prompts/demopromptid12345.json",
                "sandbox_requests": [{
                    "sandbox_request_id": "demosandboxid12345",
                    "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json",
                    "provider_call_plans": [{
                        "provider_call_plan_id": "demopcpid12345",
                        "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json"
                    }]
                }],
                "provider_responses": [{
                    "provider_response_id": "demoimportresponse12345",
                    "provider": "external-local-import",
                    "recommendation": "provider_response_review_required",
                    "artifact_path": ".atlas/research/ATLAS-DEMO/provider_responses/demoimportresponse12345.json",
                    "response_reviews": [{
                        "response_review_id": "demoreviewid12345",
                        "recommendation": "provider_response_review_ready",
                        "artifact_path": ".atlas/research/ATLAS-DEMO/response_reviews/demoreviewid12345.json"
                    }]
                }]
            }],
            "dossiers": [{
                "dossier_id": "demodossierid12345",
                "recommendation": "research_dossier_ready",
                "artifact_path": ".atlas/research/ATLAS-DEMO/dossiers/demodossierid12345.json"
            }],
            "warnings": []
        }],
        "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/prompts/{prompt_packet_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {"paper_only": True, "analysis_only": True},
            "user_context": {"symbol": symbol, "summary": "s", "thesis": "t"},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {"redacted_fragments_count": 0, "truncated": False},
            "warnings": [], "metadata": {}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "simulate-provider":
    prompt_packet_id = ARGS[2]
    provider_response_id = "demoresponseid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/provider_responses/{provider_response_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "provider_response_id": provider_response_id,
            "source_prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-mock", "provider_status": "simulated",
            "source_prompt_packet_path": f".atlas/research/{symbol}/prompts/{prompt_packet_id}.json",
            "response_summary": "Simulated response.",
            "response_sections": {"scope_review": "Scope"},
            "safety_checks": [], "passed_checks": 12, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {"redacted_fragments_count": 0},
            "warnings": [], "metadata": {}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_provider_response_created",
        "symbol": symbol, "source_prompt_packet_id": prompt_packet_id,
        "provider_response_id": provider_response_id,
        "provider": "deterministic-mock",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "review-response":
    provider_response_id = ARGS[2]
    response_review_id = "demoreviewid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/response_reviews/{response_review_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "response_reviews"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "response_review_id": response_review_id,
            "source_provider_response_id": provider_response_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-review", "review_status": "review_passed",
            "source_provider_response_path": f".atlas/research/{symbol}/provider_responses/{provider_response_id}.json",
            "checks": [], "passed_checks": 18, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {"redacted_fragments_count": 0},
            "warnings": [], "metadata": {}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_response_review_created",
        "symbol": symbol, "source_provider_response_id": provider_response_id,
        "response_review_id": response_review_id,
        "provider": "deterministic-review",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "dossier":
    run_id = ARGS[2]
    dossier_id = "demodossierid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/dossiers/{dossier_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "dossiers"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "dossier_id": dossier_id,
            "source_run_id": run_id,
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-dossier",
            "source_research_path": f".atlas/research/{symbol}/{run_id}.json",
            "workflow_status": {
                "research": True, "plans": True, "verifications": True,
                "evaluations": True, "prompts": True,
                "provider_responses": True, "response_reviews": True,
            },
            "artifact_counts": {
                "research": 1, "plans": 1, "verifications": 1,
                "evaluations": 1, "prompts": 1,
                "provider_responses": 1, "response_reviews": 1,
            },
            "linked_artifacts": [],
            "summaries": {},
            "safety_summary": {"all_local": True, "no_network_calls": True, "no_api_keys_read": True, "paper_only": True},
            "missing_links": [],
            "warnings": [],
            "recommendation": "research_dossier_ready",
            "redaction_summary": {"redacted_fragments_count": 0},
            "metadata": {}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_dossier_created",
        "symbol": symbol, "source_run_id": run_id,
        "dossier_id": dossier_id,
        "provider": "deterministic-dossier",
        "recommendation": "research_dossier_ready",
        "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            },
            {
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }
        ]
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/sandbox_requests/{sandbox_request_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    artifact = {
        "schema_version": "1",
        "artifact_type": "sandbox_request",
        "contract_version": "research_sandbox_contract_v1",
        "sandbox_request_id": sandbox_request_id,
        "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "symbol": symbol,
        "mode": "paper",
        "provider": "llm-sandbox",
        "request_payload": "payload",
        "system_boundary": {
            "paper_only": True, "analysis_only": True, "no_trading_advice": True,
            "no_live_trading_authorization": True, "no_broker_submit": True,
            "no_pending_orders": True, "no_approvals": True, "no_api_network_call": True,
            "no_financial_advice": True, "no_trading_signal_generation": True,
        },
        "explicit_boundaries": ["Local only"],
        "redaction_summary": {"redacted_fragments_count": 0, "truncated": False},
        "warnings": [],
        "metadata": {},
        "artifact_path": artifact_path,
    }
    artifact["content_hash"] = "dummyhash12345"
    with open(artifact_path, "w") as f:
        json.dump(artifact, f)
    print(json.dumps({
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    symbol = "ATLAS-DEMO"
    print(json.dumps({
        "ok": True, "status": "research_sandbox_listed",
        "items": [{
            "sandbox_request_id": "demosandboxid12345",
            "prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"
        }]
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    sandbox_request_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/sandbox_requests/{sandbox_request_id}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({
        "ok": True, "status": "research_sandbox_loaded",
        "artifact": artifact
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    sandbox_request_id = ARGS[2]
    print(json.dumps({
        "ok": True, "status": "research_sandbox_validated",
        "sandbox_request_id": sandbox_request_id,
        "valid": True, "passed_checks": 11, "failed_checks": 0,
        "checks": [], "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    sandbox_request_id = ARGS[2]
    print(json.dumps({
        "ok": True, "status": "research_sandbox_replayed",
        "sandbox_request_id": sandbox_request_id,
        "source_prompt_packet_id": "demopromptid12345",
        "match": True,
        "expected_hash": "dummyhash12345",
        "actual_hash": "dummyhash12345",
        "checks": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/provider_responses/{provider_response_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "schema_version": "1",
            "artifact_type": "provider_response",
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "response_summary": "Imported summary",
            "response_sections": [],
            "safety_checks": [],
            "limitations": [],
            "recommendation": "provider_response_review_required",
            "redaction_summary": {"redacted_fragments_count": 0, "truncated": False},
            "warnings": [],
            "artifact_path": artifact_path,
            "content_hash": "dummyhashimport12345",
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_provider_response_imported",
        "provider_response_id": provider_response_id,
        "source_sandbox_request_id": sandbox_request_id,
        "artifact_path": artifact_path,
        "recommendation": "provider_response_review_required",
        "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {"provider_id": "custom-openai-compatible", "enabled": False, "network": False},
            {"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False},
            {"provider_id": "custom-responses-compatible", "enabled": False, "network": False},
            {"provider_id": "manual-external-provider", "enabled": False, "network": False}
        ]
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/provider_call_plans/{provider_call_plan_id}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }, f)
    print(json.dumps({
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }]
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{symbol}/provider_call_plans/{provider_call_plan_id}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }))
    sys.exit(0)

print("Unknown command", file=sys.stderr)
sys.exit(1)
'''
    script = template.replace("LOG_PATH_PLACEHOLDER", str(log_path))

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(script, encoding="utf-8")
    fake_atlas.chmod(0o755)
    return workspace


def test_success_path_with_fake_atlas(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    fake_atlas = tmp_path / "bin" / "atlas"
    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "Research workflow demo complete" in result.stdout

    output = result.stdout + result.stderr
    for frag in (
        "/Users/",
        "/private/var/",
        "Authorization",
        "Bearer",
        "APCA",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "API_KEY",
        "sk-",
        "broker.example.com",
    ):
        assert frag not in output, f"Forbidden fragment in output: {frag}"
    assert str(workspace) not in output, "Absolute workspace path leaked in output"
    assert "Atlas Agent workspace created" in output

    log_path = tmp_path / "atlas_calls.log"
    assert log_path.exists()
    log_text = log_path.read_text()
    assert "research run" in log_text
    assert "research list" in log_text
    assert "research show" in log_text
    assert "research plan" in log_text
    assert "research verify" in log_text
    assert "research evaluate" in log_text
    assert "research summary" in log_text
    assert "research check-artifacts" in log_text
    assert "research timeline" in log_text
    assert "research providers" in log_text
    assert "research prompt" in log_text
    assert "research sandbox" in log_text
    assert "research sandbox-list" in log_text
    assert "research sandbox-show" in log_text
    assert "research sandbox-validate" in log_text
    assert "research sandbox-replay" in log_text
    assert "research import-provider-response" in log_text
    assert "research review-response" in log_text
    assert "research dossier" in log_text


def test_failure_if_pending_orders_created(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    # Inject a pending order file
    pending_dir = workspace / "pending_orders"
    pending_dir.mkdir(exist_ok=True)
    (pending_dir / "fake_order.json").write_text("{}")

    fake_atlas = tmp_path / "bin" / "atlas"
    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "pending orders" in result.stderr.lower() or "pending orders" in result.stdout.lower()


def test_json_unsafe_output_detection(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        """#!/usr/bin/env python3
import json, sys
print(json.dumps({"ok": True, "artifact_path": "/Users/natan/secret.json"}))
""",
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "absolute" in result.stderr.lower() or "absolute" in result.stdout.lower()


def test_missing_artifact_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        """#!/usr/bin/env python3
import json, sys
print(json.dumps({
    "ok": True, "status": "created", "run_id": "run1",
    "artifact_path": ".atlas/research/X/run1.json", "warnings": []
}))
""",
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "file not found" in result.stderr.lower() or "not found" in result.stdout.lower()


def test_missing_evaluation_artifact_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    # Return artifact_path but do NOT create the file
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "file not found" in result.stderr.lower() or "not found" in result.stdout.lower()


def test_evaluation_unsafe_output_detection(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    # Return unsafe absolute path in output
    eid = "demoevalid12345"
    artifact_path = "/Users/natan/secret.json"
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "absolute" in result.stderr.lower() or "absolute" in result.stdout.lower()


def test_check_artifacts_unsafe_output_detection(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    # Return unsafe absolute path in output
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [{{"code": "unsafe_path", "path": "/Users/natan/secret.json", "severity": "error"}}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "absolute" in result.stderr.lower() or "absolute" in result.stdout.lower()


def test_check_artifacts_failure_fails_demo(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    # Return ok=false
    print(json.dumps({{
        "ok": False, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [{{"code": "malformed_json", "path": ".atlas/research/X/bad.json", "severity": "error"}}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "ok=false" in result.stderr.lower() or "ok=false" in result.stdout.lower()


def test_pending_orders_after_check_artifacts_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    # Create a pending order during check-artifacts to trigger the guard
    pending_dir = os.path.join(".", "pending_orders")
    os.makedirs(pending_dir, exist_ok=True)
    with open(os.path.join(pending_dir, "order.json"), "w") as f:
        json.dump({{}}, f)
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "pending orders" in result.stderr.lower() or "pending orders" in result.stdout.lower()


def test_timeline_unsafe_output_detection(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Return unsafe absolute path in timeline output
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": "/Users/natan/secret.json",
            "plans": [], "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "absolute" in result.stderr.lower() or "absolute" in result.stdout.lower()


def test_timeline_failure_fails_demo(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Return ok=false
    print(json.dumps({{
        "ok": False, "status": "research_timeline",
        "entries": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "ok=false" in result.stderr.lower() or "ok=false" in result.stdout.lower()


def test_timeline_missing_lineage_fails_demo(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Return ok=true but empty entries
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "entries too low" in result.stderr.lower() or "entries too low" in result.stdout.lower()


def test_pending_orders_after_timeline_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Create a pending order during timeline to trigger the guard
    pending_dir = os.path.join(".", "pending_orders")
    os.makedirs(pending_dir, exist_ok=True)
    with open(os.path.join(pending_dir, "order.json"), "w") as f:
        json.dump({{}}, f)
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "pending orders" in result.stderr.lower() or "pending orders" in result.stdout.lower()


def test_timeline_missing_verification_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Missing verification descendant
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{"plan_id": "demoplanid12345",
                "verifications": [],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "timeline does not link" in result.stderr.lower() or "timeline does not link" in result.stdout.lower()


def test_timeline_missing_evaluation_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Missing evaluation descendant
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{"plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": []
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "timeline does not link" in result.stderr.lower() or "timeline does not link" in result.stdout.lower()


def test_timeline_command_exits_nonzero(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    # Command exits nonzero
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [], "warnings": []
    }}))
    sys.exit(2)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "ok=false" in result.stderr.lower() or "ok=false" in result.stdout.lower() or "timeline" in result.stderr.lower() or "timeline" in result.stdout.lower()


def test_providers_unsafe_output_fails_demo(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    # Return unsafe absolute path in providers output
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False,
                "description": "/Users/natan/secret"
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "absolute" in result.stderr.lower() or "absolute" in result.stdout.lower()


def test_providers_failure_fails_demo(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    # Return ok=false
    print(json.dumps({{
        "ok": False, "status": "research_providers_listed",
        "providers": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "ok=false" in result.stderr.lower() or "ok=false" in result.stdout.lower()


def test_providers_missing_deterministic_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    # No deterministic provider
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "deterministic provider" in result.stderr.lower() or "deterministic provider" in result.stdout.lower()


def test_providers_llm_accidentally_enabled_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    # LLM accidentally enabled
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": True, "default": False, "local": False,
                "network": True, "requires_api_key": True
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "llm placeholder is unsafe" in result.stderr.lower() or "llm placeholder is unsafe" in result.stdout.lower()


def test_pending_orders_after_providers_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    # Create a pending order during providers to trigger the guard
    pending_dir = os.path.join(".", "pending_orders")
    os.makedirs(pending_dir, exist_ok=True)
    with open(os.path.join(pending_dir, "order.json"), "w") as f:
        json.dump({{}}, f)
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "pending orders" in result.stderr.lower() or "pending orders" in result.stdout.lower()


def test_providers_deterministic_local_false_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": False,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "local" in result.stderr.lower() or "local" in result.stdout.lower()


def test_providers_llm_enabled_true_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": True, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "llm" in result.stderr.lower() or "llm" in result.stdout.lower() or "disabled" in result.stderr.lower() or "disabled" in result.stdout.lower()


def test_providers_llm_network_true_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": True, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0


def test_providers_llm_requires_api_key_true_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": True
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0


def test_providers_missing_llm_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    # No llm provider
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "llm" in result.stderr.lower() or "llm" in result.stdout.lower()


def test_prompt_unsafe_output_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    # Return prompt output with a forbidden fragment
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created",
        "symbol": "ATLAS-DEMO", "source_run_id": ARGS[2],
        "prompt_packet_id": "demopromptid12345",
        "artifact_path": ".atlas/research/ATLAS-DEMO/prompts/demopromptid12345.json",
        "warnings": ["Authorization: Bearer abc123"]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert (
        "forbidden" in result.stderr.lower()
        or "forbidden" in result.stdout.lower()
        or "secret-like" in result.stderr.lower()
        or "secret-like" in result.stdout.lower()
    )


def test_prompt_ok_false_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    print(json.dumps({{
        "ok": False, "status": "research_error", "message": "Prompt failed"
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "ok=false" in result.stderr.lower() or "ok=false" in result.stdout.lower() or "prompt" in result.stderr.lower()


def test_prompt_pending_orders_after_prompt_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    # Create a pending order to trigger the safety guard
    pending_dir = os.path.join(os.getcwd(), "pending_orders")
    os.makedirs(pending_dir, exist_ok=True)
    with open(os.path.join(pending_dir, "fake_order.json"), "w") as f:
        json.dump({{}}, f)
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "pending orders" in result.stderr.lower() or "pending orders" in result.stdout.lower()


def test_sandbox_show_unsafe_output_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_listed",
        "items": [{{"sandbox_request_id": "demosandboxid12345", "symbol": "ATLAS-DEMO", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"}}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_loaded",
        "artifact": {{
            "sandbox_request_id": ARGS[2],
            "symbol": "ATLAS-DEMO",
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "warnings": ["Authorization: Bearer abc123"]
        }}
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_validated",
        "valid": True, "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_replayed",
        "match": True, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "recommendation": "provider_response_review_required",
            "response_summary": "External analysis.",
            "response_sections": {{}},
            "safety_checks": [],
            "passed_checks": 0,
            "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_imported",
        "symbol": symbol,
        "sandbox_request_id": sandbox_request_id,
        "provider_response_id": provider_response_id,
        "provider": "external-local-import",
        "recommendation": "provider_response_review_required",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "review-response":
    provider_response_id = ARGS[2]
    response_review_id = "demoreviewid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/response_reviews/{{response_review_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "response_reviews"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "response_review_id": response_review_id,
            "source_provider_response_id": provider_response_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-review", "review_status": "review_passed",
            "source_provider_response_path": f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json",
            "checks": [], "passed_checks": 18, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_reviewed",
        "symbol": symbol,
        "source_provider_response_id": provider_response_id,
        "response_review_id": response_review_id,
        "review_status": "review_passed",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "dossier":
    print(json.dumps({{
        "ok": True, "status": "research_dossier_loaded",
        "symbol": "ATLAS-DEMO",
        "run_id": "demorunid12345",
        "dossier": {{
            "run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "plan_id": "demoplanid12345",
            "verification_id": "demoverifyid12345",
            "evaluation_id": "demoevalid12345",
            "prompt_packet_id": "demopromptid12345",
            "provider_response_id": "demoimportresponse12345",
            "response_review_id": "demoreviewid12345",
            "sandbox_request_id": "demosandboxid12345"
        }},
        "workflow_status": {{
            "has_research": True,
            "has_plan": True,
            "has_verification": True,
            "has_evaluation": True,
            "has_prompt": True,
            "has_provider_response": True,
            "has_response_review": True,
            "has_sandbox_request": True,
            "all_ready": True
        }},
        "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert (
        "forbidden" in result.stderr.lower()
        or "forbidden" in result.stdout.lower()
        or "secret-like" in result.stderr.lower()
        or "secret-like" in result.stdout.lower()
    )


def test_sandbox_show_ok_false_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_listed",
        "items": [{{"sandbox_request_id": "demosandboxid12345", "symbol": "ATLAS-DEMO", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"}}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    print(json.dumps({{
        "ok": False, "status": "research_error", "message": "sandbox-show failed"
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_validated",
        "valid": True, "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_replayed",
        "match": True, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "recommendation": "provider_response_review_required",
            "response_summary": "External analysis.",
            "response_sections": {{}},
            "safety_checks": [],
            "passed_checks": 0,
            "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_imported",
        "symbol": symbol,
        "sandbox_request_id": sandbox_request_id,
        "provider_response_id": provider_response_id,
        "provider": "external-local-import",
        "recommendation": "provider_response_review_required",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "review-response":
    provider_response_id = ARGS[2]
    response_review_id = "demoreviewid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/response_reviews/{{response_review_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "response_reviews"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "response_review_id": response_review_id,
            "source_provider_response_id": provider_response_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-review", "review_status": "review_passed",
            "source_provider_response_path": f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json",
            "checks": [], "passed_checks": 18, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_reviewed",
        "symbol": symbol,
        "source_provider_response_id": provider_response_id,
        "response_review_id": response_review_id,
        "review_status": "review_passed",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "dossier":
    print(json.dumps({{
        "ok": True, "status": "research_dossier_loaded",
        "symbol": "ATLAS-DEMO",
        "run_id": "demorunid12345",
        "dossier": {{
            "run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "plan_id": "demoplanid12345",
            "verification_id": "demoverifyid12345",
            "evaluation_id": "demoevalid12345",
            "prompt_packet_id": "demopromptid12345",
            "provider_response_id": "demoimportresponse12345",
            "response_review_id": "demoreviewid12345",
            "sandbox_request_id": "demosandboxid12345"
        }},
        "workflow_status": {{
            "has_research": True,
            "has_plan": True,
            "has_verification": True,
            "has_evaluation": True,
            "has_prompt": True,
            "has_provider_response": True,
            "has_response_review": True,
            "has_sandbox_request": True,
            "all_ready": True
        }},
        "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "ok=false" in result.stderr.lower() or "ok=false" in result.stdout.lower() or "sandbox-show" in result.stderr.lower()


def test_pending_orders_after_sandbox_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    # Create a pending order to trigger the safety guard
    pending_dir = os.path.join(os.getcwd(), "pending_orders")
    os.makedirs(pending_dir, exist_ok=True)
    with open(os.path.join(pending_dir, "fake_order.json"), "w") as f:
        json.dump({{}}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_listed",
        "items": [{{"sandbox_request_id": "demosandboxid12345", "symbol": "ATLAS-DEMO", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"}}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_loaded",
        "artifact": {{
            "sandbox_request_id": ARGS[2],
            "symbol": "ATLAS-DEMO",
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "warnings": []
        }}
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_validated",
        "valid": True, "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_replayed",
        "match": True, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "recommendation": "provider_response_review_required",
            "response_summary": "External analysis.",
            "response_sections": {{}},
            "safety_checks": [],
            "passed_checks": 0,
            "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_imported",
        "symbol": symbol,
        "sandbox_request_id": sandbox_request_id,
        "provider_response_id": provider_response_id,
        "provider": "external-local-import",
        "recommendation": "provider_response_review_required",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "review-response":
    provider_response_id = ARGS[2]
    response_review_id = "demoreviewid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/response_reviews/{{response_review_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "response_reviews"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "response_review_id": response_review_id,
            "source_provider_response_id": provider_response_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-review", "review_status": "review_passed",
            "source_provider_response_path": f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json",
            "checks": [], "passed_checks": 18, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_reviewed",
        "symbol": symbol,
        "source_provider_response_id": provider_response_id,
        "response_review_id": response_review_id,
        "review_status": "review_passed",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "dossier":
    print(json.dumps({{
        "ok": True, "status": "research_dossier_loaded",
        "symbol": "ATLAS-DEMO",
        "run_id": "demorunid12345",
        "dossier": {{
            "run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "plan_id": "demoplanid12345",
            "verification_id": "demoverifyid12345",
            "evaluation_id": "demoevalid12345",
            "prompt_packet_id": "demopromptid12345",
            "provider_response_id": "demoimportresponse12345",
            "response_review_id": "demoreviewid12345",
            "sandbox_request_id": "demosandboxid12345"
        }},
        "workflow_status": {{
            "has_research": True,
            "has_plan": True,
            "has_verification": True,
            "has_evaluation": True,
            "has_prompt": True,
            "has_provider_response": True,
            "has_response_review": True,
            "has_sandbox_request": True,
            "all_ready": True
        }},
        "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "pending orders" in result.stderr.lower() or "pending orders" in result.stdout.lower()


def test_timeline_lineage_success(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    fake_atlas = tmp_path / "bin" / "atlas"
    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    assert "Research workflow demo complete" in result.stdout
    # The fake atlas timeline already includes run_id -> prompt -> provider_response lineage
    # so the demo script's lineage validation should pass.


def test_timeline_missing_provider_response_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "prompts": [{{
                "prompt_packet_id": "demopromptid12345",
                "created_at": "2026-01-01T00:00:00+00:00",
                "artifact_path": ".atlas/research/ATLAS-DEMO/prompts/demopromptid12345.json",
                "sandbox_requests": [{{"sandbox_request_id": "demosandboxid12345", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json", "provider_call_plans": [{{"provider_call_plan_id": "demopcpid12345", "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json"}}]}}],
                "provider_responses": []
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "review-response":
    provider_response_id = ARGS[2]
    response_review_id = "demoreviewid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/response_reviews/{{response_review_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "response_reviews"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "response_review_id": response_review_id,
            "source_provider_response_id": provider_response_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-review", "review_status": "review_passed",
            "source_provider_response_path": f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json",
            "checks": [], "passed_checks": 18, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_response_review_created",
        "symbol": symbol, "source_provider_response_id": provider_response_id,
        "response_review_id": response_review_id,
        "provider": "deterministic-review",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "dossier":
    run_id = ARGS[2]
    dossier_id = "demodossierid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/dossiers/{{dossier_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "dossiers"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "dossier_id": dossier_id,
            "source_run_id": run_id,
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-dossier",
            "source_research_path": f".atlas/research/{{symbol}}/{{run_id}}.json",
            "workflow_status": {{
                "research": True, "plans": True, "verifications": True,
                "evaluations": True, "prompts": True,
                "provider_responses": True, "response_reviews": True,
            }},
            "artifact_counts": {{
                "research": 1, "plans": 1, "verifications": 1,
                "evaluations": 1, "prompts": 1,
                "provider_responses": 1, "response_reviews": 1,
            }},
            "linked_artifacts": [],
            "summaries": {{}},
            "safety_summary": {{"all_local": True, "no_network_calls": True, "no_api_keys_read": True, "paper_only": True}},
            "missing_links": [],
            "warnings": [],
            "recommendation": "research_dossier_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_dossier_created",
        "symbol": symbol, "source_run_id": run_id,
        "dossier_id": dossier_id,
        "provider": "deterministic-dossier",
        "recommendation": "research_dossier_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_listed",
        "items": [{{"sandbox_request_id": "demosandboxid12345", "symbol": "ATLAS-DEMO", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"}}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_loaded",
        "artifact": {{
            "sandbox_request_id": ARGS[2],
            "symbol": "ATLAS-DEMO",
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "warnings": []
        }}
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_validated",
        "valid": True, "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_replayed",
        "match": True, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "recommendation": "provider_response_review_required",
            "response_summary": "External analysis.",
            "response_sections": {{}},
            "safety_checks": [],
            "passed_checks": 0,
            "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_imported",
        "symbol": symbol,
        "sandbox_request_id": sandbox_request_id,
        "provider_response_id": provider_response_id,
        "provider": "external-local-import",
        "recommendation": "provider_response_review_required",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "provider response" in result.stderr.lower() or "provider response" in result.stdout.lower()


def test_timeline_mismatched_provider_response_id_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "prompts": [{{
                "prompt_packet_id": "demopromptid12345",
                "created_at": "2026-01-01T00:00:00+00:00",
                "artifact_path": ".atlas/research/ATLAS-DEMO/prompts/demopromptid12345.json",
                "sandbox_requests": [{{"sandbox_request_id": "demosandboxid12345", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json", "provider_call_plans": [{{"provider_call_plan_id": "demopcpid12345", "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json"}}]}}],
                "provider_responses": [{{
                    "provider_response_id": "WRONGRESPONSEID123",
                    "provider": "deterministic-mock",
                    "recommendation": "provider_response_review_ready",
                    "artifact_path": ".atlas/research/ATLAS-DEMO/provider_responses/WRONGRESPONSEID123.json"
                }}]
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_listed",
        "items": [{{"sandbox_request_id": "demosandboxid12345", "symbol": "ATLAS-DEMO", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"}}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_loaded",
        "artifact": {{
            "sandbox_request_id": ARGS[2],
            "symbol": "ATLAS-DEMO",
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "warnings": []
        }}
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_validated",
        "valid": True, "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_replayed",
        "match": True, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "recommendation": "provider_response_review_required",
            "response_summary": "External analysis.",
            "response_sections": {{}},
            "safety_checks": [],
            "passed_checks": 0,
            "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_imported",
        "symbol": symbol,
        "sandbox_request_id": sandbox_request_id,
        "provider_response_id": provider_response_id,
        "provider": "external-local-import",
        "recommendation": "provider_response_review_required",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "provider response" in result.stderr.lower() or "provider response" in result.stdout.lower()


def test_timeline_missing_prompt_fails(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "prompts": [],
            "dossiers": [],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "simulate-provider":
    prompt_packet_id = ARGS[2]
    provider_response_id = "demoresponseid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-mock", "provider_status": "simulated",
            "source_prompt_packet_path": f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json",
            "response_summary": "Simulated response.",
            "response_sections": {{}},
            "recommendation": "provider_response_review_ready",
            "safety_checks": [], "passed_checks": 0, "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_created", "symbol": symbol,
        "source_prompt_packet_id": prompt_packet_id, "provider_response_id": provider_response_id,
        "provider": "deterministic-mock", "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode != 0
    assert "prompt" in result.stderr.lower() or "prompt" in result.stdout.lower()


def test_timeline_checked_after_import_provider_response(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "atlas_calls.log"

    fake_atlas = bin_dir / "atlas"
    fake_atlas.write_text(
        f'''#!/usr/bin/env python3
import json, os, sys
ARGS = sys.argv[1:]
with open("{log_path}", "a") as f:
    f.write(" ".join(ARGS) + "\\n")

if ARGS[0] == "init":
    target = ARGS[1]
    os.makedirs(target, exist_ok=True)
    for sub in (".atlas", "memory", "audit", "pending_orders", "events", "reports", "data"):
        os.makedirs(os.path.join(target, sub), exist_ok=True)
    print("Atlas Agent workspace created.")
    sys.exit(0)

if ARGS[0] == "discipline" and ARGS[1] == "setup":
    print("Discipline profile created at .atlas/discipline.md")
    sys.exit(0)

if ARGS[0] == "config" and ARGS[1] == "set":
    print(f"Updated {{ARGS[2]}} in config.toml")
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "run":
    symbol = ARGS[2].split("=")[1] if "=" in ARGS[2] else "ATLAS-DEMO"
    run_id = "demorunid12345"
    artifact_path = f".atlas/research/{{symbol}}/{{run_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"run_id": run_id, "symbol": symbol, "mode": "paper", "artifact_path": artifact_path, "metadata": {{}}, "created_at": "2026-01-01T00:00:00+00:00"}}, f)
    print(json.dumps({{"ok": True, "status": "created", "run_id": run_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "list":
    print(json.dumps({{"ok": True, "status": "research_listed", "items": [{{"run_id": "demorunid12345", "symbol": "ATLAS-DEMO", "created_at": "2026-01-01T00:00:00+00:00", "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "provider": "deterministic", "warnings_count": 0}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "show":
    print(json.dumps({{"ok": True, "status": "research_loaded", "artifact": {{"run_id": ARGS[2], "symbol": "ATLAS-DEMO", "mode": "paper", "provider": "deterministic", "summary": "s", "thesis": "t", "market_context": "m", "risks": [], "invalidation_conditions": [], "paper_only_plan": "p", "memory_hits": [], "citations": [], "warnings": [], "artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "metadata": {{}}}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "plan":
    plan_id = "demoplanid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"plan_id": plan_id, "artifact_path": artifact_path, "metadata": {{}}}}, f)
    print(json.dumps({{"ok": True, "status": "paper_plan_created", "plan_id": plan_id, "artifact_path": artifact_path}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "verify":
    vid = "demoverifyid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/verifications/demoverifyid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "verifications"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"verification_id": vid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_verification_created", "verification_id": vid, "artifact_path": artifact_path, "recommendation": "paper_review_ready"}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "evaluate":
    eid = "demoevalid12345"
    artifact_path = ".atlas/research/ATLAS-DEMO/evaluations/demoevalid12345.json"
    os.makedirs(os.path.join(".", ".atlas", "research", "ATLAS-DEMO", "evaluations"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{"evaluation_id": eid, "artifact_path": artifact_path}}, f)
    print(json.dumps({{"ok": True, "status": "research_evaluation_created", "evaluation_id": eid, "artifact_path": artifact_path, "recommendation": "paper_evaluation_ready", "metrics": {{"row_count": 3}}}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "summary":
    print(json.dumps({{"ok": True, "status": "research_summary", "research_count": 1, "plan_count": 1, "symbols": [{{"symbol": "ATLAS-DEMO", "research_count": 1, "plan_count": 1, "latest_research_run_id": "demorunid12345", "latest_plan_id": "demoplanid12345", "latest_research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json", "latest_plan_path": ".atlas/research/ATLAS-DEMO/plans/demoplanid12345.json"}}]}}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "check-artifacts":
    print(json.dumps({{
        "ok": True, "status": "research_artifacts_checked",
        "counts": {{"research": 1, "plans": 1, "verifications": 1, "evaluations": 1}},
        "issues": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "timeline":
    print(json.dumps({{
        "ok": True, "status": "research_timeline",
        "entries": [{{
            "run_id": "demorunid12345", "symbol": "ATLAS-DEMO",
            "research_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "plans": [{{
                "plan_id": "demoplanid12345",
                "verifications": [{{"verification_id": "demoverifyid12345"}}],
                "evaluations": [{{"evaluation_id": "demoevalid12345"}}]
            }}],
            "prompts": [{{
                "prompt_packet_id": "demopromptid12345",
                "created_at": "2026-01-01T00:00:00+00:00",
                "artifact_path": ".atlas/research/ATLAS-DEMO/prompts/demopromptid12345.json",
                "sandbox_requests": [{{"sandbox_request_id": "demosandboxid12345", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json", "provider_call_plans": [{{"provider_call_plan_id": "demopcpid12345", "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json"}}]}}],
                "provider_responses": [{{
                    "provider_response_id": "demoimportresponse12345",
                    "provider": "external-local-import",
                    "recommendation": "provider_response_review_required",
                    "artifact_path": ".atlas/research/ATLAS-DEMO/provider_responses/demoimportresponse12345.json",
                    "response_reviews": [{{
                        "response_review_id": "demoreviewid12345",
                        "recommendation": "provider_response_review_ready",
                        "artifact_path": ".atlas/research/ATLAS-DEMO/response_reviews/demoreviewid12345.json"
                    }}]
                }}]
            }}],
            "dossiers": [{{
                "dossier_id": "demodossierid12345",
                "recommendation": "research_dossier_ready",
                "artifact_path": ".atlas/research/ATLAS-DEMO/dossiers/demodossierid12345.json"
            }}],
            "warnings": []
        }}],
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "providers":
    print(json.dumps({{
        "ok": True, "status": "research_providers_listed",
        "providers": [
            {{
                "name": "deterministic", "status": "available",
                "enabled": True, "default": True, "local": True,
                "network": False, "requires_api_key": False
            }},
            {{
                "name": "llm", "status": "disabled",
                "enabled": False, "default": False, "local": False,
                "network": False, "requires_api_key": False
            }}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "prompt":
    run_id = ARGS[2]
    prompt_packet_id = "demopromptid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/prompts/{{prompt_packet_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "prompts"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "prompt_packet_id": prompt_packet_id, "source_run_id": run_id,
            "symbol": symbol, "mode": "paper", "provider": "deterministic",
            "source_artifact_path": ".atlas/research/ATLAS-DEMO/demorunid12345.json",
            "max_context_chars": 8000,
            "system_boundary": {{"paper_only": True}},
            "user_context": {{"symbol": symbol}},
            "allowed_uses": ["Local analysis"],
            "forbidden_uses": ["Live trading"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_prompt_packet_created", "symbol": symbol,
        "source_run_id": run_id, "prompt_packet_id": prompt_packet_id,
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "review-response":
    provider_response_id = ARGS[2]
    response_review_id = "demoreviewid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/response_reviews/{{response_review_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "response_reviews"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "response_review_id": response_review_id,
            "source_provider_response_id": provider_response_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-review", "review_status": "review_passed",
            "source_provider_response_path": f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json",
            "checks": [], "passed_checks": 18, "failed_checks": 0,
            "recommendation": "provider_response_review_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [], "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_response_review_created",
        "symbol": symbol, "source_provider_response_id": provider_response_id,
        "response_review_id": response_review_id,
        "provider": "deterministic-review",
        "recommendation": "provider_response_review_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "dossier":
    run_id = ARGS[2]
    dossier_id = "demodossierid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/dossiers/{{dossier_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "dossiers"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "dossier_id": dossier_id,
            "source_run_id": run_id,
            "symbol": symbol, "mode": "paper",
            "provider": "deterministic-dossier",
            "source_research_path": f".atlas/research/{{symbol}}/{{run_id}}.json",
            "workflow_status": {{
                "research": True, "plans": True, "verifications": True,
                "evaluations": True, "prompts": True,
                "provider_responses": True, "response_reviews": True,
            }},
            "artifact_counts": {{
                "research": 1, "plans": 1, "verifications": 1,
                "evaluations": 1, "prompts": 1,
                "provider_responses": 1, "response_reviews": 1,
            }},
            "linked_artifacts": [],
            "summaries": {{}},
            "safety_summary": {{"all_local": True, "no_network_calls": True, "no_api_keys_read": True, "paper_only": True}},
            "missing_links": [],
            "warnings": [],
            "recommendation": "research_dossier_ready",
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "metadata": {{}}, "schema_version": "1",
            "artifact_path": artifact_path, "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_dossier_created",
        "symbol": symbol, "source_run_id": run_id,
        "dossier_id": dossier_id,
        "provider": "deterministic-dossier",
        "recommendation": "research_dossier_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox":
    prompt_packet_id = ARGS[2]
    sandbox_request_id = "demosandboxid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/sandbox_requests/{{sandbox_request_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "sandbox_requests"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "sandbox_request_id": sandbox_request_id,
            "prompt_packet_id": prompt_packet_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "system_boundary": {{"paper_only": True}},
            "explicit_boundaries": ["Local only"],
            "redaction_summary": {{"redacted_fragments_count": 0, "truncated": False}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_request_created",
        "symbol": symbol, "prompt_packet_id": prompt_packet_id,
        "source_run_id": "demorunid12345",
        "sandbox_request_id": sandbox_request_id,
        "provider": "llm-sandbox",
        "recommendation": "sandbox_request_ready",
        "artifact_path": artifact_path, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-list":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_listed",
        "items": [{{"sandbox_request_id": "demosandboxid12345", "symbol": "ATLAS-DEMO", "artifact_path": ".atlas/research/ATLAS-DEMO/sandbox_requests/demosandboxid12345.json"}}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-show":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_loaded",
        "artifact": {{
            "sandbox_request_id": ARGS[2],
            "symbol": "ATLAS-DEMO",
            "mode": "paper",
            "provider": "llm-sandbox",
            "request_payload": "payload",
            "warnings": []
        }}
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-validate":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_validated",
        "valid": True, "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "sandbox-replay":
    print(json.dumps({{
        "ok": True, "status": "research_sandbox_replayed",
        "match": True, "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "import-provider-response":
    sandbox_request_id = ARGS[2]
    provider_response_id = "demoimportresponse12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_responses/{{provider_response_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_responses"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "provider_response_id": provider_response_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_prompt_packet_id": "demopromptid12345",
            "source_run_id": "demorunid12345",
            "symbol": symbol, "mode": "paper",
            "provider": "external-local-import",
            "provider_status": "imported_untrusted",
            "recommendation": "provider_response_review_required",
            "response_summary": "External analysis.",
            "response_sections": {{}},
            "safety_checks": [],
            "passed_checks": 0,
            "failed_checks": 0,
            "redaction_summary": {{"redacted_fragments_count": 0}},
            "warnings": [],
            "metadata": {{}},
            "schema_version": "1",
            "artifact_path": artifact_path
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_response_imported",
        "symbol": symbol,
        "sandbox_request_id": sandbox_request_id,
        "provider_response_id": provider_response_id,
        "provider": "external-local-import",
        "recommendation": "provider_response_review_required",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)


if ARGS[0] == "research" and ARGS[1] == "provider-targets":
    print(json.dumps({{
        "ok": True, "status": "research_provider_targets_listed",
        "targets": [
            {{"provider_id": "custom-openai-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-chat-completions-compatible", "enabled": False, "network": False}},
            {{"provider_id": "custom-responses-compatible", "enabled": False, "network": False}},
            {{"provider_id": "manual-external-provider", "enabled": False, "network": False}}
        ]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan":
    sandbox_request_id = ARGS[2]
    provider_call_plan_id = "demopcpid12345"
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    os.makedirs(os.path.join(".", ".atlas", "research", symbol, "provider_call_plans"), exist_ok=True)
    with open(artifact_path, "w") as f:
        json.dump({{
            "schema_version": "1",
            "artifact_type": "provider_call_plan",
            "provider_call_plan_id": provider_call_plan_id,
            "source_sandbox_request_id": sandbox_request_id,
            "source_run_id": "demorunid12345",
            "symbol": symbol,
            "mode": "paper",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "provider_enabled": False,
            "network_enabled": False,
            "credentials_loaded": False,
            "provider_call_allowed": False,
            "execution_mode": "plan_only",
            "warnings": [],
            "artifact_path": artifact_path,
            "created_at": "2026-01-01T00:00:00+00:00"
        }}, f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_created",
        "provider_call_plan_id": provider_call_plan_id,
        "source_sandbox_request_id": sandbox_request_id,
        "provider_id": "custom-openai-compatible",
        "model_id": "gpt-4o",
        "artifact_path": artifact_path,
        "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-list":
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plans_listed",
        "items": [{{
            "provider_call_plan_id": "demopcpid12345",
            "source_sandbox_request_id": "demosandboxid12345",
            "source_run_id": "demorunid12345",
            "symbol": "ATLAS-DEMO",
            "created_at": "2026-01-01T00:00:00+00:00",
            "artifact_path": ".atlas/research/ATLAS-DEMO/provider_call_plans/demopcpid12345.json",
            "provider_id": "custom-openai-compatible",
            "model_id": "gpt-4o",
            "warnings_count": 0
        }}]
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-show":
    provider_call_plan_id = ARGS[2]
    symbol = "ATLAS-DEMO"
    artifact_path = f".atlas/research/{{symbol}}/provider_call_plans/{{provider_call_plan_id}}.json"
    with open(artifact_path, "r") as f:
        artifact = json.load(f)
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_loaded",
        "artifact": artifact
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-validate":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_validated",
        "provider_call_plan_id": provider_call_plan_id,
        "valid": True, "passed_checks": 13, "failed_checks": 0,
        "checks": [], "warnings": []
    }}))
    sys.exit(0)

if ARGS[0] == "research" and ARGS[1] == "provider-plan-replay":
    provider_call_plan_id = ARGS[2]
    print(json.dumps({{
        "ok": True, "status": "research_provider_call_plan_replayed",
        "provider_call_plan_id": provider_call_plan_id,
        "match": True,
        "expected_hash": "dummyhashpcp12345",
        "actual_hash": "dummyhashpcp12345",
        "checks": []
    }}))
    sys.exit(0)
print("Unknown command", file=sys.stderr)
sys.exit(1)
''',
        encoding="utf-8",
    )
    fake_atlas.chmod(0o755)

    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"stdout: {{result.stdout}}\nstderr: {{result.stderr}}"
    assert "Research workflow demo complete" in result.stdout

    # Verify command order: import-provider-response must happen before timeline lineage check
    log_text = log_path.read_text()
    sim_idx = log_text.find("research import-provider-response")
    timeline_idx = log_text.rfind("research timeline")
    assert sim_idx != -1, "import-provider-response not found in log"
    assert timeline_idx != -1, "timeline not found in log"
    assert sim_idx < timeline_idx, "timeline lineage check must happen after import-provider-response"


def test_keep_workspace_flag(fake_atlas_workspace: Path, tmp_path: Path) -> None:
    workspace = fake_atlas_workspace
    fake_atlas = tmp_path / "bin" / "atlas"
    env = os.environ.copy()
    env["ATLAS_BIN"] = str(fake_atlas)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["DEMO_WORKSPACE"] = str(workspace)

    result = subprocess.run(
        ["bash", str(SCRIPT), "--keep-workspace"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "Workspace retained" in result.stdout
