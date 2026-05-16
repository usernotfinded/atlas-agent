from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atlas_agent.research.research_report import ResearchReport
from atlas_agent.research.session import (
    DeterministicResearchProvider,
    ResearchArtifact,
    ResearchSessionError,
    UnsupportedResearchProviderError,
    run_research_session,
    sanitize_symbol,
)


class TestSanitizeSymbol:
    def test_normal_symbol(self) -> None:
        assert sanitize_symbol("AAPL") == "AAPL"
        assert sanitize_symbol("aapl") == "AAPL"
        assert sanitize_symbol("BRK.B") == "BRK.B"

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ResearchSessionError, match="empty"):
            sanitize_symbol("")

    def test_path_traversal_blocked(self) -> None:
        with pytest.raises(ResearchSessionError, match="path traversal"):
            sanitize_symbol("../etc/passwd")
        with pytest.raises(ResearchSessionError, match="path traversal"):
            sanitize_symbol("foo/bar")
        with pytest.raises(ResearchSessionError, match="path traversal"):
            sanitize_symbol("foo\\\\bar")
        with pytest.raises(ResearchSessionError, match="path traversal"):
            sanitize_symbol(".hidden")

    def test_weird_characters_stripped(self) -> None:
        assert sanitize_symbol("A@A#P$L") == "AAPL"

    def test_safe_characters_preserved(self) -> None:
        assert sanitize_symbol("BTC-USD") == "BTC-USD"


class TestDeterministicResearchProvider:
    def test_no_network_call(self) -> None:
        provider = DeterministicResearchProvider()
        report = provider.research_market("AAPL")
        assert report.provider == "deterministic"
        assert report.symbol == "AAPL"
        assert "Deterministic" in report.summary


class TestRunResearchSession:
    def test_basic_run_creates_artifact(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="AAPL",
            provider="offline",
            summary="Test summary.",
        )
        event_logger = MagicMock()

        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=event_logger,
            provider=provider,
        )

        assert isinstance(artifact, ResearchArtifact)
        assert artifact.symbol == "AAPL"
        assert artifact.mode == "paper"
        assert artifact.provider == "offline"
        assert artifact.summary == "Test summary."
        assert artifact.artifact_path.startswith(".atlas/research/AAPL/")
        assert artifact.artifact_path.endswith(".json")
        assert artifact.thesis
        assert artifact.market_context
        assert len(artifact.risks) > 0
        assert len(artifact.invalidation_conditions) > 0
        assert artifact.paper_only_plan
        assert artifact.warnings == []
        assert artifact.metadata["provider_requested"] == "deterministic"

        artifact_file = tmp_path / artifact.artifact_path
        assert artifact_file.exists()
        data = json.loads(artifact_file.read_text())
        assert data["symbol"] == "AAPL"
        assert data["mode"] == "paper"
        assert data["provider"] == "offline"
        assert data["summary"] == "Test summary."
        assert data["run_id"] == artifact.run_id
        assert "created_at" in data
        assert "thesis" in data
        assert "market_context" in data
        assert "risks" in data
        assert "invalidation_conditions" in data
        assert "paper_only_plan" in data
        assert "warnings" in data
        assert "metadata" in data

        provider.research_market.assert_called_once_with("AAPL")

    def test_event_logged(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="TSLA",
            provider="offline",
            summary="Tesla summary.",
        )
        event_logger = MagicMock()

        artifact = run_research_session(
            symbol="TSLA",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=event_logger,
            provider=provider,
        )

        event_logger.write.assert_called_once()
        call = event_logger.write.call_args
        assert call.kwargs["run_id"] == artifact.run_id
        assert call.kwargs["command"] == "atlas research run"
        assert call.kwargs["mode"] == "paper"
        payload = call.kwargs["payload"]
        assert payload["symbol"] == "TSLA"
        assert payload["provider"] == "offline"
        assert "artifact_path" in payload
        assert payload["status"] == "created"
        assert "memory_hits_count" not in payload
        assert "summary" not in payload
        assert "thesis" not in payload

    def test_no_event_logger_does_not_crash(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="GOOG",
            provider="offline",
            summary="Google summary.",
        )

        artifact = run_research_session(
            symbol="GOOG",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider=provider,
        )

        assert artifact.symbol == "GOOG"

    def test_memory_dir_missing_is_ok(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="META",
            provider="offline",
            summary="Meta summary.",
        )
        event_logger = MagicMock()
        missing_memory = tmp_path / "nonexistent_memory"

        artifact = run_research_session(
            symbol="META",
            workspace_path=tmp_path,
            memory_dir=missing_memory,
            event_logger=event_logger,
            provider=provider,
        )

        assert artifact.memory_hits == []
        assert artifact.symbol == "META"

    def test_use_memory_false_skips_memory(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="MSFT",
            provider="offline",
            summary="MSFT summary.",
        )
        event_logger = MagicMock()
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "notes.md").write_text("MSFT looks interesting today.")

        artifact = run_research_session(
            symbol="MSFT",
            workspace_path=tmp_path,
            memory_dir=memory_dir,
            event_logger=event_logger,
            provider=provider,
            use_memory=False,
        )

        assert artifact.memory_hits == []

    def test_symbol_sanitized_before_use(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="AAPL",
            provider="offline",
            summary="Summary.",
        )
        event_logger = MagicMock()

        artifact = run_research_session(
            symbol="aapl",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=event_logger,
            provider=provider,
        )

        assert artifact.symbol == "AAPL"
        provider.research_market.assert_called_once_with("AAPL")

    def test_citations_preserved(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="NVDA",
            provider="perplexity",
            summary="NVDA summary.",
            citations=("https://example.com/1", "https://example.com/2"),
        )
        event_logger = MagicMock()

        artifact = run_research_session(
            symbol="NVDA",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=event_logger,
            provider=provider,
        )

        assert artifact.citations == ("https://example.com/1", "https://example.com/2")
        artifact_file = tmp_path / artifact.artifact_path
        data = json.loads(artifact_file.read_text())
        assert data["citations"] == ["https://example.com/1", "https://example.com/2"]

    def test_unsupported_provider_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedResearchProviderError, match="unsupported_research_provider"):
            run_research_session(
                symbol="AAPL",
                workspace_path=tmp_path,
                memory_dir=None,
                event_logger=None,
                provider_name="openai",
            )

    def test_provider_name_deterministic_uses_deterministic(self, tmp_path: Path) -> None:
        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider_name="deterministic",
        )
        assert artifact.provider == "deterministic"

    def test_artifact_no_absolute_paths(self, tmp_path: Path) -> None:
        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider_name="deterministic",
        )
        assert not artifact.artifact_path.startswith("/")
        assert "/Users/" not in artifact.artifact_path
        assert "/private/var/" not in artifact.artifact_path

    def test_artifact_paper_only_plan_no_live_language(self, tmp_path: Path) -> None:
        artifact = run_research_session(
            symbol="AAPL",
            workspace_path=tmp_path,
            memory_dir=None,
            event_logger=None,
            provider_name="deterministic",
        )
        plan_lower = artifact.paper_only_plan.lower()
        assert "live-submit" not in plan_lower
        assert "authorize" not in plan_lower

    def test_event_payload_no_memory_snippets(self, tmp_path: Path) -> None:
        provider = MagicMock()
        provider.research_market.return_value = ResearchReport(
            symbol="AMZN",
            provider="offline",
            summary="AMZN summary.",
        )
        event_logger = MagicMock()
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        (memory_dir / "notes.md").write_text("AMZN looks interesting today.")

        run_research_session(
            symbol="AMZN",
            workspace_path=tmp_path,
            memory_dir=memory_dir,
            event_logger=event_logger,
            provider=provider,
        )

        payload = event_logger.write.call_args.kwargs["payload"]
        assert "memory_hits" not in payload
        assert "summary" not in payload
        assert "thesis" not in payload

    def test_no_execution_path_called(self, tmp_path: Path) -> None:
        with patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route, \
             patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval, \
             patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
            artifact = run_research_session(
                symbol="AAPL",
                workspace_path=tmp_path,
                memory_dir=None,
                event_logger=None,
                provider_name="deterministic",
            )
            assert artifact.symbol == "AAPL"
            mock_route.assert_not_called()
            mock_approval.assert_not_called()
            mock_broker.assert_not_called()
