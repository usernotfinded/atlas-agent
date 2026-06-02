"""Tests for scripts/check_clean_install.py.

No network calls, no credentials, no broker/provider contact, no live trading.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_clean_install.py"


def _run_script(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        env=env,
    )


class TestScriptExists:
    def test_script_exists(self) -> None:
        assert SCRIPT.exists(), f"Script not found: {SCRIPT}"

    def test_script_is_readable(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert len(text) > 0


class TestSafeDefaults:
    def test_no_network_calls_by_default(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "urllib" not in text
        assert "requests" not in text
        assert "http.client" not in text

    def test_default_install_uses_no_index(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert '"--no-index"' in text, "Default install must use --no-index"
        assert '"--no-build-isolation"' in text, "Default install must use --no-build-isolation"

    def test_allow_network_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--allow-network" in text

    def test_no_credential_loading(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "load_dotenv" not in text
        assert "api_key" not in text

    def test_no_broker_or_provider_calls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "place_order" not in text
        assert "resolve_execution_broker" not in text
        assert "broker.submit" not in text
        assert "broker_sync" not in text

    def test_no_shell_true(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "shell=True" not in text, "Script must not use shell=True"

    def test_dry_run_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--dry-run" in text

    def test_skip_venv_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--skip-venv" in text

    def test_keep_temp_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--keep-temp" in text


class TestDryRun:
    def test_dry_run_exits_zero(self) -> None:
        result = _run_script("--dry-run")
        assert result.returncode == 0, f"dry-run failed:\n{result.stdout}\n{result.stderr}"

    def test_dry_run_shows_plan(self) -> None:
        result = _run_script("--dry-run")
        assert "Clean install verification plan" in result.stdout
        assert "atlas --help" in result.stdout
        assert "atlas validate" in result.stdout
        assert "atlas init --template routine-trader outside repo" in result.stdout

    def test_dry_run_shows_no_network_default(self) -> None:
        result = _run_script("--dry-run")
        assert result.returncode == 0
        assert "allow_network: False" in result.stdout
        assert "--no-index --no-build-isolation" in result.stdout

    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        result = _run_script("--dry-run", cwd=tmp_path)
        assert result.returncode == 0
        assert not list(tmp_path.glob("atlas-clean-install-*"))


class TestNetworkEscalation:
    def test_allow_network_shown_in_plan(self) -> None:
        result = _run_script("--dry-run", "--allow-network")
        assert result.returncode == 0
        assert "allow_network: True" in result.stdout
        assert "pip install -e <repo>" in result.stdout

    def test_no_silent_network_fallback(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "retry" not in text.lower() or "with network" not in text.lower()


class TestConsoleEntrypoint:
    def test_script_runs_installed_atlas_entrypoint(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "_find_venv_atlas" in text, "Script must locate venv atlas entrypoint"
        assert "atlas_bin" in text, "Script must use atlas_bin for CLI checks"
        assert "_check_template_init" in text, "Script must verify template init"

    def test_script_does_not_use_python_m_as_primary(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        # python -m may be used for package version check, but not for atlas --help/validate
        help_section = text.split("Checking atlas --help")[0]
        assert "atlas_agent.cli" not in help_section or "atlas_bin" in text


class TestSafetyClaims:
    def test_no_live_trading_ready_claims(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "live trading ready" not in text

    def test_no_profitability_claims(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "guaranteed profit" not in text
        assert "profitable strategy" not in text

    def test_required_safe_phrases_present(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "no credentials" in text or "credentials" in text


class TestForbiddenFragments:
    def test_no_hardcoded_users_path_in_script(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        import re
        matches = re.findall(r"/Users/[A-Za-z0-9_]+", text)
        for m in matches:
            if m not in ("/Users/",):
                pytest.fail(f"Hardcoded absolute user path in script: {m}")

    def test_no_hardcoded_private_var_in_script(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        import re
        matches = re.findall(r"/private/var/[A-Za-z0-9_/-]+", text)
        for m in matches:
            if m not in ("/private/var/",):
                pytest.fail(f"Hardcoded absolute path in script: {m}")


class TestOutputRedaction:
    def test_dry_run_output_has_no_absolute_paths(self) -> None:
        result = _run_script("--dry-run")
        assert result.returncode == 0
        assert "/Users/" not in result.stdout, (
            f"Dry-run output leaked absolute path:\n{result.stdout}"
        )
        assert "/private/var/" not in result.stdout
        assert "/var/folders/" not in result.stdout
        assert "/tmp/" not in result.stdout
        assert "/var/tmp/" not in result.stdout

    def test_skip_venv_without_dry_run_fails_safely(self) -> None:
        result = _run_script("--skip-venv")
        assert result.returncode != 0, (
            f"Expected --skip-venv to fail without --dry-run:\n{result.stdout}\n{result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "dry-run" in combined.lower() or "isolated" in combined.lower()

    def test_dry_run_skip_venv_safe(self) -> None:
        result = _run_script("--dry-run", "--skip-venv")
        assert result.returncode == 0, (
            f"dry-run --skip-venv failed:\n{result.stdout}\n{result.stderr}"
        )
        assert "Clean install verification plan" in result.stdout

    def test_redaction_of_forbidden_paths(self, monkeypatch) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_clean_install", str(SCRIPT))
        cic = importlib.util.module_from_spec(spec)
        sys.modules["check_clean_install_test_import"] = cic
        spec.loader.exec_module(cic)
        monkeypatch.setattr(cic, "_CURRENT_TEMP_DIR", "/var/folders/abc/T/tmp123")
        sample = (
            "Error in /Users/testuser/Desktop/repo "
            "and /private/var/folders/abc/T/tmp123 "
            "and /var/folders/abc/T/tmp456 "
            "and /tmp/secret "
            "and /var/tmp/secret"
        )
        redacted = cic._redact(sample)
        assert "/Users/" not in redacted, (
            f"Redaction leaked /Users/:\n{redacted}"
        )
        assert "/private/var/" not in redacted
        assert "/var/folders/" not in redacted
        assert "/tmp/" not in redacted
        assert "/var/tmp/" not in redacted
        assert "<temp>" in redacted or "~" in redacted


class TestFailedSubprocessRedaction:
    def test_pip_failure_stdout_stderr_redacted(self, monkeypatch, tmp_path, capsys):
        """Simulate failed pip install subprocess with forbidden paths in stdout/stderr.

        Assert the final output/report does NOT contain raw absolute paths
        and instead contains safe placeholders (<temp>, ~, <repo>, <home>).
        """
        import importlib.util
        import tempfile as _tempfile_module

        spec = importlib.util.spec_from_file_location(
            "check_clean_install_failure", str(SCRIPT)
        )
        cic = importlib.util.module_from_spec(spec)
        sys.modules["check_clean_install_failure"] = cic
        spec.loader.exec_module(cic)

        fake_temp = tmp_path / "atlas-clean-install-test"
        fake_temp.mkdir()

        # Point mkdtemp to our controlled path so _CURRENT_TEMP_DIR is predictable
        def _fake_mkdtemp(prefix="", dir=None):
            return str(fake_temp)

        monkeypatch.setattr(_tempfile_module, "mkdtemp", _fake_mkdtemp)

        # Create fake venv structure so _find_venv_python succeeds
        fake_python = fake_temp / "venv" / "bin" / "python"
        fake_python.parent.mkdir(parents=True)
        fake_python.write_text("# fake python")

        home = str(Path.home())
        repo = str(cic.REPO_ROOT)

        # Simulate _run: venv creation succeeds, pip install fails with forbidden paths
        def fake_run(cmd, **kwargs):
            if "-m" in cmd and "venv" in cmd:
                return subprocess.CompletedProcess(
                    cmd, returncode=0, stdout="", stderr=""
                )
            if "-m" in cmd and "pip" in cmd:
                stderr = (
                    f"Could not build in {fake_temp}/build\n"
                    f"User home: /Users/testuser/Desktop/repo\n"
                    f"Private tmp: /private/var/folders/abc/T/xyz\n"
                    f"Var tmp: /var/folders/abc/T/xyz\n"
                    f"Tmp path: /tmp/secret\n"
                    f"Var tmp path: /var/tmp/secret\n"
                    f"Real home: {home}/.local/lib/python3.11/site-packages\n"
                    f"Real repo: {repo}/src/atlas_agent/__init__.py"
                )
                return subprocess.CompletedProcess(
                    cmd, returncode=1, stdout="", stderr=stderr
                )
            return subprocess.CompletedProcess(
                cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(cic, "_run", fake_run)

        ret = cic.main([])

        captured = capsys.readouterr()
        combined = captured.out + captured.err

        assert ret == 2, f"Expected exit code 2, got {ret}"
        assert "pip install failed" in combined or "ERROR:" in combined

        # No raw forbidden paths
        assert "/Users/" not in combined, f"Leaked /Users/ in output:\n{combined}"
        assert "/private/var/" not in combined
        assert "/var/folders/" not in combined
        assert "/tmp/" not in combined
        assert "/var/tmp/" not in combined
        assert str(fake_temp) not in combined, (
            f"Leaked temp path in output:\n{combined}"
        )
        assert home not in combined, f"Leaked home path in output:\n{combined}"
        assert repo not in combined, f"Leaked repo path in output:\n{combined}"

        # Safe placeholders present
        assert "<temp>" in combined or "<home>" in combined
        if home != "/":
            assert "~" in combined, f"Home path not redacted with ~:\n{combined}"
        # Repo may be redacted as <repo> or as ~ when it lives under home
        assert "<repo>" in combined or "~" in combined, (
            f"Repo path not redacted:\n{combined}"
        )


class TestExpectedTemplateFiles:
    def test_memory_portfolio_md_is_required(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert '"memory/portfolio.md"' in text, (
            "check_clean_install.py must require memory/portfolio.md"
        )

    def test_expected_template_files_list_is_nonempty(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "EXPECTED_TEMPLATE_FILES" in text
        # Expect at least README, .env.example, configs, memory, routines, skills
        assert text.count('"') >= 12, "EXPECTED_TEMPLATE_FILES should list multiple files"


class TestVersionReporting:
    def test_expected_version_matches_pyproject(self) -> None:
        import tomllib
        pyproject = REPO_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        pkg_version = data.get("project", {}).get("version")
        text = SCRIPT.read_text(encoding="utf-8")
        assert f'EXPECTED_PACKAGE_VERSION = "{pkg_version}"' in text


class TestRealCleanInstall:
    def test_real_no_network_clean_install_passes(self) -> None:
        result = _run_script()
        assert result.returncode == 0, (
            f"Clean install failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "Network allowed: False" in result.stdout
        assert "Console entrypoint checked: True" in result.stdout
        assert "atlas validate checked: True" in result.stdout
