"""Tests for README quickstart verification — Batch 9.9 + 10.0.

This batch is documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
README_PATH = REPO_ROOT / "README.md"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_readme_quickstart.py"


def _read(path: Path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _lower(text: str) -> str:
    return text.lower()


def _run_script_on_text(text: str) -> subprocess.CompletedProcess[str]:
    """Run verify_readme_quickstart.py against a temporary README."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(text)
        f.flush()
        tmp_path = f.name

    original_script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    # Patch the hardcoded README_PATH to point at our temp file
    patched_script = original_script.replace(
        'README_PATH = REPO_ROOT / "README.md"',
        f'README_PATH = Path("{tmp_path}")',
    )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(patched_script)
        f.flush()
        tmp_script = f.name

    return subprocess.run(
        [sys.executable, tmp_script],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# README structure
# ---------------------------------------------------------------------------


class TestReadmeQuickstartStructure:
    def test_readme_has_quickstart_heading(self) -> None:
        text = _read(README_PATH)
        assert "## Quickstart" in text

    def test_readme_has_install_step(self) -> None:
        text = _read(README_PATH)
        lower = _lower(text)
        assert "install" in lower

    def test_readme_has_backtest_example(self) -> None:
        text = _read(README_PATH)
        assert "atlas backtest run" in text

    def test_readme_has_validate_example(self) -> None:
        text = _read(README_PATH)
        assert "atlas validate" in text

    def test_readme_has_atlas_help_example(self) -> None:
        text = _read(README_PATH)
        assert "atlas --help" in text


# ---------------------------------------------------------------------------
# README safety wording
# ---------------------------------------------------------------------------


class TestReadmeQuickstartSafetyWording:
    def test_sandbox_only_present(self) -> None:
        text = _read(README_PATH)
        assert "sandbox-only" in _lower(text)

    def test_paper_first_present(self) -> None:
        text = _read(README_PATH)
        assert "paper-first" in _lower(text)

    def test_offline_safe_present(self) -> None:
        text = _read(README_PATH)
        assert "offline-safe" in _lower(text)

    def test_live_trading_disabled_by_default_present(self) -> None:
        text = _read(README_PATH)
        assert "live trading disabled by default" in _lower(text)

    def test_not_financial_advice_present(self) -> None:
        text = _read(README_PATH)
        assert "not financial advice" in _lower(text)

    def test_no_broker_order_path_present(self) -> None:
        text = _read(README_PATH)
        assert "no broker/order path" in _lower(text)

    def test_no_credentials_loaded_present(self) -> None:
        text = _read(README_PATH)
        assert "no credentials loaded" in _lower(text)

    def test_profitability_limitation_present(self) -> None:
        text = _read(README_PATH)
        lower = _lower(text)
        assert "safety validation does not imply profitability" in lower
        # Accept combined form "profitability or trading correctness"
        assert (
            "safety validation does not imply trading correctness" in lower
            or "does not imply profitability or trading correctness" in lower
        )


# ---------------------------------------------------------------------------
# README forbidden claims
# ---------------------------------------------------------------------------


class TestReadmeQuickstartNoForbiddenClaims:
    FORBIDDEN_PHRASES = (
        "live trading ready",
        "production trading ready",
        "safe to trade",
        "trust granted",
        "provider execution enabled",
        "broker execution enabled",
        "orders enabled",
        "approvals enabled",
        "autonomous trading ready",
    )

    def _sentence_around(self, text: str, start: int, end: int) -> str:
        boundary_chars = {'.', '!', '?', '\n'}
        s = start
        while s > 0 and text[s - 1] not in boundary_chars:
            s -= 1
        e = end
        while e < len(text) and text[e] not in boundary_chars:
            e += 1
        return text[s:e]

    def _assert_absent_outside_negative_context(self, text: str, phrase: str) -> bool:
        lower_text = text.lower()
        phrase_lower = phrase.lower()
        for m in re.finditer(re.escape(phrase_lower), lower_text):
            sentence = self._sentence_around(lower_text, m.start(), m.end()).lower()
            negative_indicators = (
                "not ",
                "does not",
                "never",
                "no ",
                "avoid",
                "disclaimer",
                "prohibited",
                "forbidden",
                "must not",
                "cannot",
                "do not",
                "is not",
                "are not",
                "without",
                "fail closed",
                "not yet",
                "not implemented",
                "not enabled",
                "not authorized",
                "not a ",
                "not ready",
                "remains disabled",
                "remains locked",
                "remains blocked",
            )
            if not any(ind in sentence for ind in negative_indicators):
                return False
        return True

    def test_no_forbidden_claims(self) -> None:
        text = _read(README_PATH)
        for phrase in self.FORBIDDEN_PHRASES:
            assert self._assert_absent_outside_negative_context(
                text, phrase
            ), f"Forbidden claim '{phrase}' found outside negative context in README"


# ---------------------------------------------------------------------------
# README forbidden fragments
# ---------------------------------------------------------------------------


class TestReadmeQuickstartNoForbiddenFragments:
    def test_no_users_path(self) -> None:
        text = _read(README_PATH)
        assert "/Users/" not in text, "Absolute /Users/ path found in README"

    def test_no_private_var_path(self) -> None:
        text = _read(README_PATH)
        assert "/private/var/" not in text, "Absolute /private/var/ path found in README"

    def test_no_secret_placeholders_in_bash_blocks(self) -> None:
        text = _read(README_PATH)
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
            for line in block.splitlines():
                if line.strip().startswith("#"):
                    continue
                if re.search(r"\bsk-[A-Za-z0-9]+", line):
                    raise AssertionError(f"Secret-like placeholder in README bash block: {line.strip()}")
                for token in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"):
                    comment_pos = line.find("#")
                    if comment_pos != -1:
                        before = line[:comment_pos]
                        if re.search(rf"\b{token}\b", before):
                            raise AssertionError(
                                f"Credential-like token '{token}' in README bash block: {line.strip()}"
                            )
                    else:
                        if re.search(rf"\b{token}\b", line):
                            raise AssertionError(
                                f"Credential-like token '{token}' in README bash block: {line.strip()}"
                            )


# ---------------------------------------------------------------------------
# Verification script
# ---------------------------------------------------------------------------


class TestVerifyReadmeQuickstartScript:
    def test_script_exists(self) -> None:
        assert VERIFY_SCRIPT.exists(), f"Verification script not found: {VERIFY_SCRIPT}"

    def test_script_passes_on_current_readme(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERIFY_SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"verify_readme_quickstart.py failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_script_rejects_live_trading_claim(self) -> None:
        text = "# README\n\n```bash\natlas --help\n```\n\nLive trading ready.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected script to reject live trading ready claim"
        assert "live trading ready" in result.stdout.lower()

    def test_script_rejects_unsafe_command(self) -> None:
        text = "# README\n\n```bash\ncurl https://example.com\n```\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected script to reject curl command"
        assert "curl" in result.stdout.lower()

    def test_script_rejects_missing_safe_phrase(self) -> None:
        text = "# README\n\n```bash\natlas --help\n```\n\nNot financial advice.\n"
        # Missing sandbox-only, paper-first, offline-safe, live trading disabled by default
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected script to reject missing safe phrases"

    def test_script_accepts_negative_context(self) -> None:
        text = (
            "# README\n\n```bash\npython3.11 -m pip install -e .\natlas --help\natlas validate\n"
            "atlas backtest run --data data/sample/ohlcv.csv --symbol DEMO-SYMBOL\n"
            "```\n\n"
            "Sandbox-only, paper-first, offline-safe. Live trading disabled by default.\n"
            "Not financial advice. Safety validation does not imply profitability.\n"
            "Safety validation does not imply trading correctness.\n"
            "Live trading is not ready.\n"
        )
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected script to accept negative context:\n{result.stdout}"
        )

    def test_script_rejects_secret_placeholder(self) -> None:
        text = (
            "# README\n\n```bash\natlas --help\nexport API_KEY=sk-abc123\n```\n\n"
            "Sandbox-only, paper-first, offline-safe. Live trading disabled by default.\n"
            "Not financial advice. Safety validation does not imply profitability.\n"
            "Safety validation does not imply trading correctness.\n"
        )
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected script to reject secret placeholder"
        assert "sk-" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Command path safety
# ---------------------------------------------------------------------------


class TestReadmeQuickstartCommandPaths:
    def test_bash_commands_use_relative_paths_only(self) -> None:
        text = _read(README_PATH)
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
            for line in block.splitlines():
                if line.strip().startswith("atlas ") or line.strip().startswith("pip "):
                    assert "/Users/" not in line, f"Absolute path in command: {line}"
                    assert "/private/" not in line, f"Absolute path in command: {line}"

    def test_no_secret_tokens_in_any_bash_line(self) -> None:
        text = _read(README_PATH)
        for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
            for line in block.splitlines():
                if line.strip().startswith("#"):
                    continue
                for token in ("API_KEY", "SECRET", "TOKEN", "PASSWORD"):
                    comment_pos = line.find("#")
                    if comment_pos != -1:
                        before = line[:comment_pos]
                        assert not re.search(rf"\b{token}\b", before), (
                            f"Credential token '{token}' in bash block: {line.strip()}"
                        )
                    else:
                        assert not re.search(rf"\b{token}\b", line), (
                            f"Credential token '{token}' in bash block: {line.strip()}"
                        )
