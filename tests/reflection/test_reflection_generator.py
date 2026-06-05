"""Tests for atlas_agent.reflection.generator."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from atlas_agent.reflection.generator import generate_reflection
from atlas_agent.reflection.models import ReflectionStatus


class TestGenerateReflection:
    def test_from_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "report.md"
            test_file.write_text("# Report\n\nSome data.\n", encoding="utf-8")
            artifact = generate_reflection(test_file, kind="report", workspace=tmpdir)
            assert artifact.status == ReflectionStatus.draft
            assert artifact.provenance.input_artifact.kind == "report"
            assert artifact.provenance.input_artifact.path == str(test_file)
            assert artifact.provenance.input_artifact.input_hash
            assert artifact.output.provider_execution_disabled is True
            assert artifact.output.static_fallback is True

    def test_from_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "missing.md"
            artifact = generate_reflection(test_file, kind="report", workspace=tmpdir)
            assert artifact.provenance.input_artifact.kind == "report"
            assert "No input data available" in artifact.output.summary

    def test_kind_detection_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "daily-report.md"
            test_file.write_text("# Daily\n", encoding="utf-8")
            artifact = generate_reflection(test_file, workspace=tmpdir)
            assert artifact.provenance.input_artifact.kind == "report"

    def test_kind_detection_backtest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "backtest" / "result.json"
            test_file.parent.mkdir()
            test_file.write_text('{"run_id": "bt-1"}', encoding="utf-8")
            artifact = generate_reflection(test_file, workspace=tmpdir)
            assert artifact.provenance.input_artifact.kind == "backtest"

    def test_no_fake_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "input.md"
            test_file.write_text("# Real Data\n\nContent.\n", encoding="utf-8")
            artifact = generate_reflection(test_file, workspace=tmpdir)
            observations_str = " ".join(artifact.output.observations)
            assert "placeholder" not in observations_str.lower()
            assert "todo" not in observations_str.lower()
            assert "lorem ipsum" not in observations_str.lower()

    def test_provider_disabled_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "input.md"
            test_file.write_text("data", encoding="utf-8")
            artifact = generate_reflection(test_file, workspace=tmpdir)
            assert artifact.output.provider_execution_disabled is True
            assert artifact.output.static_fallback is True

    def test_provenance_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "input.md"
            test_file.write_text("data", encoding="utf-8")
            artifact = generate_reflection(test_file, workspace=tmpdir)
            assert artifact.provenance.generator_version
            assert artifact.provenance.generated_at
            assert artifact.provenance.workspace == str(tmpdir)

    def test_disclaimer_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "input.md"
            test_file.write_text("data", encoding="utf-8")
            artifact = generate_reflection(test_file, workspace=tmpdir)
            assert "not financial advice" in artifact.disclaimer.lower()
