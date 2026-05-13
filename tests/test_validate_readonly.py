from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from atlas_agent.cli import main
from atlas_agent.config import AtlasConfig
from atlas_agent.diagnostics.readiness import run_diagnostics

@pytest.fixture
def clean_workspace():
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        main(["init", ".", "--template", "routine-trader"])
        yield Path(temp_dir)
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)

def test_validate_is_read_only(clean_workspace, capsys):
    def get_file_list(d: Path) -> set[str]:
        return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}

    files_before = get_file_list(clean_workspace)
    
    code = main(["validate"])
    assert code == 0
    _ = capsys.readouterr()
    
    files_after = get_file_list(clean_workspace)
    assert files_before == files_after, "validate created files"

def test_validate_json_is_read_only(clean_workspace, capsys):
    def get_file_list(d: Path) -> set[str]:
        return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}

    files_before = get_file_list(clean_workspace)
    
    code = main(["validate", "--json"])
    assert code == 0
    _ = capsys.readouterr()
    
    files_after = get_file_list(clean_workspace)
    assert files_before == files_after, "validate --json created files"


def test_validate_strict_is_read_only(clean_workspace, capsys):
    def get_file_list(d: Path) -> set[str]:
        return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}

    files_before = get_file_list(clean_workspace)

    code = main(["validate", "--strict"])
    assert code in (0, 2)
    _ = capsys.readouterr()

    files_after = get_file_list(clean_workspace)
    assert files_before == files_after, "validate --strict created files"


def test_validate_json_strict_is_read_only(clean_workspace, capsys):
    def get_file_list(d: Path) -> set[str]:
        return {str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()}

    files_before = get_file_list(clean_workspace)

    code = main(["validate", "--json", "--strict"])
    assert code in (0, 2)
    _ = capsys.readouterr()

    files_after = get_file_list(clean_workspace)
    assert files_before == files_after, "validate --json --strict created files"


def test_validate_invalid_config_reports_error_without_mutating_files(clean_workspace, capsys):
    config_path = clean_workspace / ".atlas" / "config.toml"
    secret_like_value = "sk-secret-validate-should-not-leak"
    config_path.write_text(
        f'[broker]\nenable_live_trading = "{secret_like_value}"\n',
        encoding="utf-8",
    )

    def snapshot_files(d: Path) -> dict[str, bytes]:
        return {
            str(path.relative_to(d)): path.read_bytes()
            for path in d.rglob("*")
            if path.is_file()
        }

    before = snapshot_files(clean_workspace)
    code = main(["validate"])
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    after = snapshot_files(clean_workspace)

    assert code == 1
    assert "Configuration error:" in combined
    assert "Invalid Atlas config schema" in combined
    assert secret_like_value not in combined
    assert before == after, "validate mutated files when config is invalid"


def test_readiness_audit_logging_checks_use_config_audit_flags(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    config = AtlasConfig(
        workspace_root=tmp_path,
        memory_dir=tmp_path / "memory",
    )
    config.audit.log_raw_prompts = True
    config.audit.log_provider_text = True

    report = run_diagnostics(config)
    by_id = {check.id: check for check in report.checks}

    raw_prompt_check = by_id["audit.raw_prompt_logging"]
    provider_text_check = by_id["audit.provider_text_logging"]

    assert raw_prompt_check.status == "warn"
    assert "Enabled" in raw_prompt_check.message
    assert provider_text_check.status == "warn"
    assert "Enabled" in provider_text_check.message


def test_readiness_audit_logging_checks_ignore_safety_shadow_fields(tmp_path: Path) -> None:
    (tmp_path / ".atlas").mkdir(parents=True, exist_ok=True)
    config = AtlasConfig(
        workspace_root=tmp_path,
        memory_dir=tmp_path / "memory",
    )
    config.audit.log_raw_prompts = False
    config.audit.log_provider_text = False

    # Shadow fields on safety must not influence audit logging readiness checks.
    object.__setattr__(config.safety, "log_raw_prompts", True)
    object.__setattr__(config.safety, "log_provider_text", True)

    report = run_diagnostics(config)
    by_id = {check.id: check for check in report.checks}

    assert by_id["audit.raw_prompt_logging"].status == "info"
    assert by_id["audit.raw_prompt_logging"].message == "Disabled."
    assert by_id["audit.provider_text_logging"].status == "info"
    assert by_id["audit.provider_text_logging"].message == "Disabled."
