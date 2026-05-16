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
    print(f"Atlas Agent workspace created: {target} (template: routine-trader)")
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

    log_path = tmp_path / "atlas_calls.log"
    assert log_path.exists()
    log_text = log_path.read_text()
    assert "research run" in log_text
    assert "research list" in log_text
    assert "research show" in log_text
    assert "research plan" in log_text
    assert "research verify" in log_text
    assert "research summary" in log_text


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
