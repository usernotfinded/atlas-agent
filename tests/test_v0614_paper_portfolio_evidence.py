import json
import subprocess
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_v0614_paper_portfolio_evidence.py"
JSON_FILE = ROOT / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
MD_FILE = ROOT / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"


def run_script() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def run_script_json() -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_script_passes_on_current_repo():
    result = run_script()
    assert result.returncode == 0, f"Checker failed: {result.stdout}\n{result.stderr}"
    assert "PASSED" in result.stdout


def test_script_json_parses():
    data = run_script_json()
    assert data["artifact_type"] == "v0614_paper_portfolio_evidence_check"
    assert data["valid"] is True
    assert data["errors"] == []


def test_fails_if_json_omits_candidate(tmp_path, monkeypatch):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    
    # Write a valid MD
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text())

    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_demos", "required_checkers", "required_tests"]:
        data[key] = []
    # Omit CAND-006
    data["candidates"] = [c for c in data["candidates"] if c["id"] != "CAND-006"]
    test_json.write_text(json.dumps(data))

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "candidates must exactly list" in result.stdout


def test_fails_if_source_version_wrong(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text())

    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_demos", "required_checkers", "required_tests"]:
        data[key] = []
    data["source_version"] = "0.6.14"
    test_json.write_text(json.dumps(data))

    # Also mock pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "source_version must be '0.6.13'" in result.stdout


def test_fails_if_evidence_claims_released(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text() + "\n" * 200 + "v0.6.14 is released")

    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_demos", "required_checkers", "required_tests"]:
        data[key] = []
    test_json.write_text(json.dumps(data))

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "v0.6.14 is released" in result.stdout.lower()


def test_fails_on_live_ready_wording(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text() + "\n" * 200 + "This is live ready")

    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_demos", "required_checkers", "required_tests"]:
        data[key] = []
    test_json.write_text(json.dumps(data))

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unsafe claim" in result.stdout


def test_fails_on_guaranteed_profit_wording(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text() + "\n" * 200 + "guaranteed profit")

    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_demos", "required_checkers", "required_tests"]:
        data[key] = []
    test_json.write_text(json.dumps(data))

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "unsafe claim" in result.stdout


def test_fails_on_missing_demo_script(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text())

    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_checkers", "required_tests"]:
        data[key] = []
    data["required_demos"] = ["scripts/demo_nonexistent.sh"]
    test_json.write_text(json.dumps(data))

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "references missing file: scripts/demo_nonexistent.sh" in result.stdout


def test_fails_if_demo_references_live_mode(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text())

    demo = tmp_path / "scripts" / "demo_paper_portfolio_proposal.sh"
    demo.parent.mkdir(parents=True)
    demo.write_text("atlas backtest --mode live")
    
    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_checkers", "required_tests"]:
        data[key] = []
    data["required_demos"] = ["scripts/demo_paper_portfolio_proposal.sh"]
    test_json.write_text(json.dumps(data))

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "references live mode" in result.stdout


def test_fails_if_demo_references_order_submission(tmp_path):
    test_json = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.json"
    test_json.parent.mkdir(parents=True)
    test_md = tmp_path / "docs" / "releases" / "v0.6.14-paper-portfolio-evidence.md"
    test_md.write_text(MD_FILE.read_text())

    demo = tmp_path / "scripts" / "demo_paper_portfolio_proposal.sh"
    demo.parent.mkdir(parents=True)
    demo.write_text("atlas submit")
    
    data = json.loads(JSON_FILE.read_text())
    for key in ["required_docs", "required_checkers", "required_tests"]:
        data[key] = []
    data["required_demos"] = ["scripts/demo_paper_portfolio_proposal.sh"]
    test_json.write_text(json.dumps(data))

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.6.13"')
    init_py = tmp_path / "src" / "atlas_agent" / "__init__.py"
    init_py.parent.mkdir(parents=True)
    init_py.write_text('__version__ = "0.6.13"')

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "references order submission" in result.stdout
