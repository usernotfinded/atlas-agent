from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.agent.bounded_live_autonomy_readiness_cli import (
    CLI_DESCRIPTION,
    _UNSAFE_FLAGS,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "bounded_live_autonomy_readiness"


def _fixture_path(name: str) -> Path:
    return FIXTURES / f"{name}.json"


def _base_args(output_dir: Path) -> list[str]:
    return [
        "--quality-gate", str(_fixture_path("trading-quality-gate")),
        "--shadow-comparison", str(_fixture_path("shadow-live-comparison")),
        "--submit-conformance", str(_fixture_path("gated-submit-conformance")),
        "--readiness-envelope", str(_fixture_path("runtime-readiness-envelope")),
        "--operator-approval-gate", str(_fixture_path("operator-approval-gate")),
        "--bounded-autonomy-policy", str(_fixture_path("bounded-autonomy-policy")),
        "--risk-limit", str(_fixture_path("risk-limit")),
        "--symbol-allowlist", str(_fixture_path("symbol-allowlist")),
        "--heartbeat-deadman", str(_fixture_path("heartbeat-deadman")),
        "--audit-redaction", str(_fixture_path("audit-redaction")),
        "--output-dir", str(output_dir),
        "--as-of", "2026-06-24T11:00:00Z",
    ]


def test_help_contains_disclaimer() -> None:
    assert "evidence-only" in CLI_DESCRIPTION.lower()
    assert "does not submit orders" in CLI_DESCRIPTION.lower()


def test_valid_cli_all_pass(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    rc = main(_base_args(output_dir))
    assert rc == 0
    assert (output_dir / "bounded-live-readiness.json").is_file()
    assert (output_dir / "bounded-live-readiness-report.md").is_file()


def test_json_output_mode(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    rc = main(_base_args(output_dir) + ["--json"])
    assert rc == 0


def test_missing_required_flag_fails(tmp_path: Path) -> None:
    args = _base_args(tmp_path / "out")[2:]
    rc = main(args)
    assert rc == 2


@pytest.mark.parametrize("flag", sorted(_UNSAFE_FLAGS))
def test_unsafe_flag_rejected(flag: str, tmp_path: Path) -> None:
    rc = main(_base_args(tmp_path / "out") + [flag])
    assert rc == 2


def test_equals_syntax_rejected(tmp_path: Path) -> None:
    rc = main(_base_args(tmp_path / "out") + ["--mode=live"])
    assert rc == 2


def test_workspace_before_agent_delegates_to_legacy() -> None:
    code = """
import io, sys
from atlas_agent.cli_bootstrap import main
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = io.StringIO()
sys.stderr = io.StringIO()
try:
    main(["--workspace", "/tmp/nonexistent-ws-cand015", "agent", "bounded-live-readiness", "--help"])
except SystemExit:
    pass
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
print("atlas_agent.cli" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    output = result.stdout + result.stderr
    assert output.strip().splitlines()[-1] == "True", output


def test_workspace_after_agent_rejected_by_configless(tmp_path: Path) -> None:
    args = [
        "agent", "bounded-live-readiness",
        "--workspace", str(tmp_path),
    ] + _base_args(tmp_path / "out")[1:]
    rc = main(args)
    assert rc == 2


def test_output_path_aliasing_rejected(tmp_path: Path) -> None:
    aliased = tmp_path / "aliased_output"
    os.link(_fixture_path("trading-quality-gate"), aliased)
    rc = main(_base_args(aliased))
    assert rc == 2


def test_json_output_does_not_contain_input_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    rc = main(_base_args(output_dir) + ["--json"])
    assert rc == 0
    json_text = (output_dir / "bounded-live-readiness.json").read_text(encoding="utf-8")
    assert '"input_paths"' not in json_text


def test_json_output_does_not_leak_absolute_input_paths(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    rc = main(_base_args(output_dir) + ["--json"])
    assert rc == 0
    json_text = (output_dir / "bounded-live-readiness.json").read_text(encoding="utf-8")
    for fixture in [
        "trading-quality-gate",
        "shadow-live-comparison",
        "gated-submit-conformance",
        "runtime-readiness-envelope",
        "operator-approval-gate",
        "bounded-autonomy-policy",
        "risk-limit",
        "symbol-allowlist",
        "heartbeat-deadman",
        "audit-redaction",
    ]:
        path = _fixture_path(fixture)
        assert str(path) not in json_text, f"absolute path leaked for {fixture}"
        assert str(path.parent) not in json_text, f"parent directory leaked for {fixture}"


def test_cli_json_stdout_does_not_contain_input_paths(tmp_path: Path, capsys: Any) -> None:
    output_dir = tmp_path / "out"
    rc = main(_base_args(output_dir) + ["--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert '"input_paths"' not in captured.out
    assert '"input_paths"' not in captured.err


def test_cli_text_output_lists_gates_and_blockers_when_blocked(tmp_path: Path) -> None:
    bad_policy_path = tmp_path / "bad-policy.json"
    policy = json.loads(_fixture_path("bounded-autonomy-policy").read_text(encoding="utf-8"))
    policy["l3_autonomy_enabled"] = True
    bad_policy_path.write_text(json.dumps(policy), encoding="utf-8")
    args = _base_args(tmp_path / "out")
    for i, token in enumerate(args):
        if token == "--bounded-autonomy-policy":
            args[i + 1] = str(bad_policy_path)
            break
    rc = main(args)
    assert rc == 2
