from __future__ import annotations

import re
from pathlib import Path

from atlas_agent.deploy import DEPLOYMENT_FILES, ensure_deploy_files
from atlas_agent.safety.secrets import scan_text_for_secrets


SECRET_VALUE_PATTERN = re.compile(
    r"\b(?:sk-|pplx-|xox[baprs]-|akia)[A-Za-z0-9_-]{10,}",
    flags=re.IGNORECASE,
)


def test_deploy_templates_do_not_embed_secret_values() -> None:
    for files in DEPLOYMENT_FILES.values():
        for content in files.values():
            assert scan_text_for_secrets(content) == []
            assert SECRET_VALUE_PATTERN.search(content) is None


def test_generated_deploy_files_do_not_embed_secret_values(tmp_path: Path) -> None:
    generated_paths: list[Path] = []
    for target in DEPLOYMENT_FILES:
        generated_paths.extend(
            generated.path for generated in ensure_deploy_files(target, base_dir=tmp_path)
        )

    assert generated_paths
    for path in generated_paths:
        content = path.read_text(encoding="utf-8")
        assert scan_text_for_secrets(content) == []
        assert SECRET_VALUE_PATTERN.search(content) is None


def test_systemd_service_runs_continuous_agent() -> None:
    service = DEPLOYMENT_FILES["systemd"][Path("deploy/systemd/atlas-agent.service")]

    assert "ExecStart=/usr/local/bin/atlas agent run --continuous" in service
    assert "--mode live" not in service
