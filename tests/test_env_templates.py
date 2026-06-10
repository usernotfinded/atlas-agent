from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
CHECKER = REPO_ROOT / "scripts" / "check_env_templates.py"


def _run_checker(*extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *extra_args],
        capture_output=True,
        text=True,
    )


class TestEnvTemplateCheckerRealRepo:
    def test_checker_passes_on_real_repo(self) -> None:
        result = _run_checker()
        assert result.returncode == 0, result.stdout


class TestEnvTemplateCheckerSynthetic:
    def test_detects_non_empty_secret(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text("ALPACA_API_KEY=secret_value\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "ALPACA_API_KEY: secret key must be empty" in result.stdout

    def test_detects_blocked_placeholder(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text("ANTHROPIC_API_KEY=YOUR_API_KEY_HERE\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "blocked placeholder" in result.stdout

    def test_detects_sk_prefix(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text("OPENAI_COMPATIBLE_API_KEY=sk-test123\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "blocked prefix" in result.stdout

    def test_detects_bearer_prefix(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text("CLICKUP_API_TOKEN=Bearer abc123\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "blocked prefix" in result.stdout

    def test_detects_missing_safety_default(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text("TRADING_MODE=paper\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "ENABLE_LIVE_TRADING: missing required safety default" in result.stdout

    def test_detects_wrong_safety_default(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        env_file.write_text("ENABLE_LIVE_TRADING=true\nTRADING_MODE=paper\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "ENABLE_LIVE_TRADING: safety default mismatch" in result.stdout

    def test_detects_template_parity_mismatch(self, tmp_path: Path) -> None:
        root = tmp_path / ".env.example"
        tmpl = tmp_path / "templates" / "routine-trader" / ".env.example"
        tmpl.parent.mkdir(parents=True)
        root.write_text("TRADING_MODE=paper\nENABLE_LIVE_TRADING=false\nMINIMUM_CONFIDENCE=0.6\n")
        tmpl.write_text("TRADING_MODE=paper\nENABLE_LIVE_TRADING=false\nMINIMUM_CONFIDENCE=0.55\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "value mismatch for 'MINIMUM_CONFIDENCE'" in result.stdout

    def test_allows_safe_non_empty_defaults(self, tmp_path: Path) -> None:
        lines = [
            "TRADING_MODE=paper",
            "ENABLE_LIVE_TRADING=false",
            "ORDER_APPROVAL_MODE=manual_live",
            "REQUIRE_ORDER_APPROVAL=true",
            "ALLOW_LEVERAGE=false",
            "KILL_SWITCH_ENABLED=false",
            "ALPACA_BASE_URL=https://paper-api.alpaca.markets",
            "DATA_PATH=data/sample/ohlcv.csv",
            "MAX_DAILY_LOSS=100",
        ]
        text = "\n".join(lines) + "\n"
        (tmp_path / ".env.example").write_text(text)
        (tmp_path / "templates" / "routine-trader").mkdir(parents=True)
        (tmp_path / "templates" / "routine-trader" / ".env.example").write_text(text)
        (tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader").mkdir(parents=True)
        (tmp_path / "src" / "atlas_agent" / "templates" / "routine-trader" / ".env.example").write_text(text)
        result = _run_checker(str(tmp_path))
        assert result.returncode == 0, result.stdout

    def test_detects_unexpected_non_empty_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env.example"
        lines = [
            "TRADING_MODE=paper",
            "ENABLE_LIVE_TRADING=false",
            "ORDER_APPROVAL_MODE=manual_live",
            "REQUIRE_ORDER_APPROVAL=true",
            "ALLOW_LEVERAGE=false",
            "KILL_SWITCH_ENABLED=false",
            "MY_UNKNOWN_VAR=should_be_empty",
        ]
        env_file.write_text("\n".join(lines) + "\n")
        result = _run_checker(str(tmp_path))
        assert result.returncode == 1
        assert "MY_UNKNOWN_VAR: unexpected non-empty value" in result.stdout
