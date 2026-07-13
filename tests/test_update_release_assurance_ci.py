import json
import subprocess
from pathlib import Path

import pytest

from scripts.update_release_assurance_ci import (
    CORE_WORKFLOWS,
    filter_core_runs,
    format_json_runs,
    format_md_table,
    update_json_file,
    update_md_file,
)


@pytest.fixture
def sample_runs():
    return [
        {
            "name": "CI",
            "databaseId": 123,
            "url": "https://github.com/org/repo/actions/runs/123",
            "conclusion": "success",
            "status": "completed",
            "createdAt": "2026-07-13T10:00:00Z",
        },
        {
            "name": "Release Gate",
            "databaseId": 124,
            "url": "https://github.com/org/repo/actions/runs/124",
            "conclusion": "success",
            "status": "completed",
            "createdAt": "2026-07-13T10:05:00Z",
        },
        {
            "name": "CI",
            "databaseId": 125,
            "url": "https://github.com/org/repo/actions/runs/125",
            "conclusion": "failure",
            "status": "completed",
            "createdAt": "2026-07-13T09:00:00Z",
        },
        {
            "name": "Unknown Workflow",
            "databaseId": 126,
            "url": "https://github.com/org/repo/actions/runs/126",
            "conclusion": "success",
            "status": "completed",
            "createdAt": "2026-07-13T10:10:00Z",
        },
    ]


def test_filter_core_runs_keeps_most_recent(sample_runs):
    result = filter_core_runs(sample_runs)
    names = [r["name"] for r in result]
    assert names == ["CI", "Release Gate"]
    assert result[0]["databaseId"] == 123  # first CI, not older 125


def test_format_md_table(sample_runs):
    filtered = filter_core_runs(sample_runs)
    table = format_md_table(filtered)
    assert "| Workflow | Run | Conclusion |" in table
    assert "| CI | [123](https://github.com/org/repo/actions/runs/123) | success |" in table
    assert "| Release Gate | [124](https://github.com/org/repo/actions/runs/124) | success |" in table


def test_format_json_runs(sample_runs):
    filtered = filter_core_runs(sample_runs)
    runs = format_json_runs(filtered)
    assert runs[0] == {
        "name": "CI",
        "run_id": 123,
        "url": "https://github.com/org/repo/actions/runs/123",
        "conclusion": "success",
        "created_at": "2026-07-13T10:00:00Z",
    }


def test_update_md_file(tmp_path):
    md = tmp_path / "assurance.md"
    md.write_text(
        "# Assurance\n\n## GitHub Actions / CI Status\n\nplaceholder\n\n## Safety\n\nsafe.\n",
        encoding="utf-8",
    )
    update_md_file(md, "| Workflow | Run |\n|---|---|\n| CI | [123](url) |")
    content = md.read_text(encoding="utf-8")
    assert "## GitHub Actions / CI Status" in content
    assert "placeholder" not in content
    assert "| CI | [123](url) |" in content
    assert "## Safety" in content


def test_update_json_file(tmp_path, sample_runs):
    json_file = tmp_path / "assurance.json"
    json_file.write_text(
        json.dumps({"release": "v0.6.23", "ci_status": {"status": "placeholder"}}),
        encoding="utf-8",
    )
    filtered = filter_core_runs(sample_runs)
    update_json_file(json_file, filtered)
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["ci_status"]["status"] == "recorded"
    assert data["ci_status"]["runs"][0]["name"] == "CI"


def test_main_dry_run_does_not_mutate(tmp_path, monkeypatch):
    md = tmp_path / "assurance.md"
    md.write_text(
        "# Assurance\n\n## GitHub Actions / CI Status\n\nplaceholder\n\n",
        encoding="utf-8",
    )
    jf = tmp_path / "assurance.json"
    jf.write_text(
        json.dumps({"release": "v0.6.23", "ci_status": {"status": "placeholder"}}),
        encoding="utf-8",
    )

    def fake_release_exists(tag):
        return True

    def fake_fetch_runs(tag):
        return [
            {
                "name": "CI",
                "databaseId": 999,
                "url": "https://example.com/999",
                "conclusion": "success",
                "status": "completed",
                "createdAt": "2026-07-13T10:00:00Z",
            }
        ]

    monkeypatch.setattr(
        "scripts.update_release_assurance_ci.release_exists", fake_release_exists
    )
    monkeypatch.setattr(
        "scripts.update_release_assurance_ci.fetch_runs", fake_fetch_runs
    )

    from scripts.update_release_assurance_ci import main

    assert main(["--tag", "v0.6.23", "--md", str(md), "--json", str(jf)]) == 0
    assert "placeholder" in md.read_text(encoding="utf-8")
    assert json.loads(jf.read_text(encoding="utf-8"))["ci_status"]["status"] == "placeholder"


def test_main_missing_release(monkeypatch):
    monkeypatch.setattr(
        "scripts.update_release_assurance_ci.release_exists", lambda tag: False
    )
    from scripts.update_release_assurance_ci import main

    assert main(["--tag", "v0.6.99", "--md", "x.md", "--json", "x.json"]) == 1
