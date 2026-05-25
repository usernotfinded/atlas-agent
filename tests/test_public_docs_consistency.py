"""Tests for public docs consistency script — Batch 10.0.

Documentation/test-only. No execution code, no network calls,
no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_public_docs_consistency.py"


def _run_script_on_text(text: str) -> subprocess.CompletedProcess[str]:
    """Run the consistency script with a temporary doc under REPO_ROOT.

    The temporary doc is placed inside a temp directory under REPO_ROOT
    so that Path.relative_to(REPO_ROOT) works in the script.
    """
    tmp_dir = Path(tempfile.mkdtemp(dir=REPO_ROOT))
    tmp_path = tmp_dir / "test_doc.md"
    tmp_path.write_text(text, encoding="utf-8")

    original_script = SCRIPT.read_text(encoding="utf-8")
    # Replace the entire PUBLIC_DOC_PATHS list so only the temp doc is scanned
    old_paths_block = (
        'PUBLIC_DOC_PATHS = [\n'
        '    REPO_ROOT / "README.md",\n'
        '    REPO_ROOT / "docs" / "provider-safety-dossier.md",\n'
        '    REPO_ROOT / "docs" / "examples" / "provider-safety-dossier-workflow.md",\n'
        '    REPO_ROOT / "docs" / "release-checklist.md",\n'
        '    REPO_ROOT / "docs" / "release-candidate-readiness.md",\n'
        '    REPO_ROOT / "docs" / "release-candidate-cutover.md",\n'
        ']'
    )
    new_paths_block = f'PUBLIC_DOC_PATHS = [Path("{tmp_path}")]'
    patched_script = original_script.replace(old_paths_block, new_paths_block)

    tmp_script = tmp_dir / "check.py"
    tmp_script.write_text(patched_script, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(tmp_script)],
        capture_output=True,
        text=True,
    )
    # Clean up temp files
    try:
        tmp_path.unlink()
        tmp_script.unlink()
        tmp_dir.rmdir()
    except OSError:
        pass
    return result


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"


class TestScriptPassesOnCurrentDocs:
    def test_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Public docs consistency script failed:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptRejectsUnsafePositiveClaims:
    def test_rejects_live_trading_ready(self) -> None:
        text = "# Doc\n\n```bash\natlas --help\n```\n\nLive trading ready.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0, "Expected failure on live trading ready claim"
        assert "live trading ready" in result.stdout.lower()

    def test_rejects_provider_execution_enabled(self) -> None:
        text = "# Doc\n\nProvider execution enabled.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "provider execution enabled" in result.stdout.lower()

    def test_rejects_guaranteed_profit(self) -> None:
        text = "# Doc\n\nThis strategy produces guaranteed profit.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "guaranteed profit" in result.stdout.lower()


class TestScriptAcceptsNegativeSafetyWording:
    def test_accepts_not_live_trading_ready(self) -> None:
        text = "# Doc\n\nLive trading is not ready.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for negative wording:\n{result.stdout}\n{result.stderr}"
        )

    def test_accepts_live_trading_disabled(self) -> None:
        text = "# Doc\n\nLive trading remains disabled by default.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for disabled wording:\n{result.stdout}\n{result.stderr}"
        )

    def test_accepts_provider_execution_locked(self) -> None:
        text = "# Doc\n\nProvider execution remains locked.\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode == 0, (
            f"Expected pass for locked wording:\n{result.stdout}\n{result.stderr}"
        )


class TestScriptRejectsAbsolutePaths:
    def test_rejects_users_path(self) -> None:
        text = "# Doc\n\n```bash\ncd /Users/natan/dev\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "/Users/" in result.stdout

    def test_rejects_private_var_path(self) -> None:
        text = "# Doc\n\n```bash\ncd /private/var/tmp\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "/private/var/" in result.stdout


class TestScriptRejectsForbiddenFragments:
    def test_rejects_sk_token(self) -> None:
        text = "# Doc\n\n```bash\nexport KEY=sk-abc123def456\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "sk-" in result.stdout.lower()

    def test_rejects_bearer_token(self) -> None:
        text = "# Doc\n\n```bash\ncurl -H 'Authorization: Bearer xyz123'\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "bearer" in result.stdout.lower()


class TestScriptRejectsUnsafeCommands:
    def test_rejects_curl(self) -> None:
        text = "# Doc\n\n```bash\ncurl https://api.example.com\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "curl" in result.stdout.lower()

    def test_rejects_order_create(self) -> None:
        text = "# Doc\n\n```bash\natlas order create --symbol AAPL\n```\nNot financial advice.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "order create" in result.stdout.lower()


class TestScriptRequiresNotFinancialAdvice:
    def test_requires_not_financial_advice(self) -> None:
        text = "# Doc\n\nSome safe text.\n"
        result = _run_script_on_text(text)
        assert result.returncode != 0
        assert "not financial advice" in result.stdout.lower()
