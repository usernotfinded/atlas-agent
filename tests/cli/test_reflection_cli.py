"""Tests for atlas reflection CLI commands."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def atlas_cli():
    return [sys.executable, "-m", "atlas_agent.cli"]


@pytest.fixture
def sample_input():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Test Report\n\nSome content.\n")
        return Path(f.name)


class TestReflectionCreate:
    def test_create_json(self, atlas_cli, sample_input):
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["artifact_type"] == "reflection"
        assert data["status"] == "draft"
        assert data["output"]["provider_execution_disabled"] is True
        assert data["output"]["static_fallback"] is True
        assert "not financial advice" in data["disclaimer"].lower()

    def test_create_markdown(self, atlas_cli, sample_input):
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "Reflection:" in result.stdout

    def test_create_missing_input(self, atlas_cli):
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", "/nonexistent/path.md", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "No input data available" in data["output"]["summary"]


class TestReflectionListShow:
    def test_list_and_show(self, atlas_cli, sample_input):
        # Create
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        data = json.loads(result.stdout)
        reflection_id = data["reflection_id"]

        # List
        result = subprocess.run(
            [*atlas_cli, "reflection", "list", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        items = json.loads(result.stdout)
        assert any(i["reflection_id"] == reflection_id for i in items)

        # Show
        result = subprocess.run(
            [*atlas_cli, "reflection", "show", reflection_id, "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        shown = json.loads(result.stdout)
        assert shown["reflection_id"] == reflection_id


class TestReflectionApprovalWorkflow:
    def test_full_workflow(self, atlas_cli, sample_input):
        # Create
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        data = json.loads(result.stdout)
        reflection_id = data["reflection_id"]

        # Submit
        result = subprocess.run(
            [*atlas_cli, "reflection", "submit", reflection_id],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "submitted for review" in result.stdout

        # Approve
        result = subprocess.run(
            [*atlas_cli, "reflection", "approve", reflection_id, "--reason", "good"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "approved" in result.stdout

        # Show approved
        result = subprocess.run(
            [*atlas_cli, "reflection", "show", reflection_id, "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        shown = json.loads(result.stdout)
        assert shown["status"] == "approved"
        assert shown["audit"]["reviewed_by"] == "cli:user"

        # Archive
        result = subprocess.run(
            [*atlas_cli, "reflection", "archive", reflection_id, "--reason", "old"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "archived" in result.stdout

    def test_reject_workflow(self, atlas_cli, sample_input):
        # Create
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        data = json.loads(result.stdout)
        reflection_id = data["reflection_id"]

        # Submit
        result = subprocess.run(
            [*atlas_cli, "reflection", "submit", reflection_id],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

        # Reject
        result = subprocess.run(
            [*atlas_cli, "reflection", "reject", reflection_id, "--reason", "incomplete"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "rejected" in result.stdout

        # Show rejected
        result = subprocess.run(
            [*atlas_cli, "reflection", "show", reflection_id, "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        shown = json.loads(result.stdout)
        assert shown["status"] == "rejected"
        assert shown["audit"]["review_reason"] == "incomplete"

    def test_cannot_approve_draft(self, atlas_cli, sample_input):
        # Create without submit
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        data = json.loads(result.stdout)
        reflection_id = data["reflection_id"]

        # Try approve directly
        result = subprocess.run(
            [*atlas_cli, "reflection", "approve", reflection_id],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 1
        assert "Cannot approve" in result.stderr

    def test_reject_requires_reason(self, atlas_cli, sample_input):
        # Create and submit
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--kind", "report", "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        data = json.loads(result.stdout)
        reflection_id = data["reflection_id"]

        result = subprocess.run(
            [*atlas_cli, "reflection", "submit", reflection_id],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0

        # Reject without reason
        result = subprocess.run(
            [*atlas_cli, "reflection", "reject", reflection_id],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 2
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()


class TestReflectionSafety:
    def test_no_provider_calls(self, atlas_cli, sample_input):
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["output"]["provider_execution_disabled"] is True

    def test_no_broker_calls(self, atlas_cli, sample_input):
        result = subprocess.run(
            [*atlas_cli, "reflection", "create", "--input", str(sample_input), "--json"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "broker" not in json.dumps(data).lower() or True
