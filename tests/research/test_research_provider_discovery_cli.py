from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_agent.cli import main


def _config(tmp_path: Path):
    from atlas_agent.config import AtlasConfig

    cfg = AtlasConfig(
        workspace_dir=tmp_path,
        data_dir=tmp_path / "data",
        memory_dir=tmp_path / "memory",
        audit_dir=tmp_path / "audit",
        events_dir=tmp_path / "events",
        reports_dir=tmp_path / "reports",
        pending_orders_dir=tmp_path / "pending_orders",
    )
    return cfg


class TestProviderDiscoveryTextOutput:
    def test_providers_text_output(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers"])
        assert code == 0
        out = capsys.readouterr().out
        assert "deterministic" in out.lower()
        assert "available" in out.lower()
        assert "status: disabled" in out.lower() or "llm" in out.lower()
        assert "network: no" in out.lower() or "network: false" in out.lower()
        assert "requires api key: no" in out.lower() or "requires api key: false" in out.lower()
        assert "external llm research providers are not enabled" in out.lower()

    def test_no_secrets_or_paths_in_text(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers"])
        assert code == 0
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out
        assert "Authorization" not in out
        assert "Bearer" not in out
        assert "APCA" not in out
        assert "SECRET" not in out
        assert "TOKEN" not in out
        assert "PASSWORD" not in out
        assert "sk-" not in out


class TestProviderDiscoveryJsonOutput:
    def test_providers_json_output(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["ok"] is True
        assert data["status"] == "research_providers_listed"
        assert isinstance(data["providers"], list)
        names = {p["name"] for p in data["providers"]}
        assert "deterministic" in names
        det = next(p for p in data["providers"] if p["name"] == "deterministic")
        assert det["enabled"] is True
        assert det["default"] is True
        assert det["network"] is False
        assert det["requires_api_key"] is False
        disabled = [p for p in data["providers"] if not p["enabled"]]
        assert len(disabled) >= 1
        assert all(not p["network"] for p in disabled)
        assert all(not p["requires_api_key"] for p in disabled)

    def test_json_no_secrets_or_paths(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert "/Users/" not in out
        assert "/private/var/" not in out
        assert "Authorization" not in out
        assert "Bearer" not in out
        assert "APCA" not in out
        assert "SECRET" not in out
        assert "TOKEN" not in out
        assert "PASSWORD" not in out
        assert "sk-" not in out


class TestProviderDiscoveryNoEnvReads:
    def test_no_api_key_leak_with_env_set(self, tmp_path: Path, capsys, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-LEAKEDSECRET123")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ANTHROPICSECRET123")
        monkeypatch.setenv("GOOGLE_API_KEY", "GOOGLESECRET123")
        monkeypatch.setenv("APCA_API_KEY_ID", "APCASECRET123")
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers"])
        assert code == 0
        out = capsys.readouterr().out
        assert "LEAKEDSECRET" not in out
        assert "ANTHROPICSECRET" not in out
        assert "GOOGLESECRET" not in out
        assert "APCASECRET" not in out
        assert "sk-" not in out

        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers", "--json"])
        assert code == 0
        out = capsys.readouterr().out
        assert "LEAKEDSECRET" not in out
        assert "ANTHROPICSECRET" not in out
        assert "GOOGLESECRET" not in out
        assert "APCASECRET" not in out
        assert "sk-" not in out


class TestProviderDiscoveryNoNetworkImports:
    PROVIDERS_PATH = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "research" / "providers.py"
    CLI_PATH = Path(__file__).resolve().parents[2] / "src" / "atlas_agent" / "cli.py"

    def _source(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _check_no_banned_imports(self, path: Path) -> None:
        src = self._source(path)
        banned = [
            "import openai",
            "import anthropic",
            "import google.generativeai",
            "import requests",
            "import httpx",
            "urllib.request",
        ]
        for imp in banned:
            assert imp not in src, f"Banned import '{imp}' found in {path}"

    def test_providers_source_no_network_imports(self) -> None:
        self._check_no_banned_imports(self.PROVIDERS_PATH)

    RESEARCH_PROVIDERS_HANDLER_PATH = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "atlas_agent"
        / "cli_commands"
        / "research"
        / "provider_misc.py"
    )

    def test_cli_providers_handler_no_network_imports(self) -> None:
        src = self._source(self.RESEARCH_PROVIDERS_HANDLER_PATH)
        # Find the providers handler block
        start = src.find("def handle_providers(")
        assert start != -1
        end = src.find("\ndef ", start + 1)
        block = src[start : end if end != -1 else len(src)]
        assert 'if args.command == "research" and args.research_command == "providers":' in block
        banned = [
            "import openai",
            "import anthropic",
            "import google.generativeai",
            "import requests",
            "import httpx",
            "urllib.request",
        ]
        for imp in banned:
            assert imp not in block, f"Banned import '{imp}' found in providers CLI handler"


class TestProviderDiscoveryNoExecutionPath:
    def test_no_broker_or_order_router_called(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            with patch("atlas_agent.brokers.resolver.BrokerResolver.resolve_execution_broker") as mock_broker:
                with patch("atlas_agent.execution.order_router.OrderRouter.route") as mock_route:
                    with patch("atlas_agent.execution.approval.ApprovalManager.create_pending_order") as mock_approval:
                        code = main(["research", "providers"])
        assert code == 0
        mock_broker.assert_not_called()
        mock_route.assert_not_called()
        mock_approval.assert_not_called()


class TestProviderDiscoveryReadOnly:
    def test_creates_no_artifacts_or_pending_orders(self, tmp_path: Path, monkeypatch) -> None:
        config = _config(tmp_path)
        config.ensure_dirs()
        monkeypatch.chdir(tmp_path)
        before = set(tmp_path.rglob("*"))
        with patch("atlas_agent.cli.AtlasConfig.from_env", return_value=config):
            code = main(["research", "providers"])
        assert code == 0
        after = set(tmp_path.rglob("*"))
        assert before == after, f"Files changed: {after - before}"
