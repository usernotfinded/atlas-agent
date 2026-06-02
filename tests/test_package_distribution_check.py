"""Tests for scripts/check_package_distribution.py.

No network calls, no credentials, no broker/provider contact, no live trading.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_package_distribution.py"

PACKAGE_VERSION = "0.5.7rc7"
PUBLIC_TAG = "v0.5.8-rc7"

CURRENT_PACKAGE_VERSION = "0.5.9.dev0"


def _run_script(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=cwd or REPO_ROOT,
        env=env,
    )


def _make_fake_wheel(path: Path, name: str = "atlas_agent", version: str = PACKAGE_VERSION) -> None:
    """Create a minimal fake wheel with METADATA and entry_points.txt."""
    with zipfile.ZipFile(path, "w") as zf:
        metadata = (
            f"Metadata-Version: 2.1\n"
            f"Name: {name}\n"
            f"Version: {version}\n"
            f"Summary: Atlas Agent test wheel\n"
        )
        zf.writestr("atlas_agent-0.0.0.dist-info/METADATA", metadata)
        entry_points = "[console_scripts]\natlas = atlas_agent.cli:main\n"
        zf.writestr("atlas_agent-0.0.0.dist-info/entry_points.txt", entry_points)


def _write_fake_wheel_templates(zf: zipfile.ZipFile) -> None:
    for rel in (
        "templates/routine-trader/README.md",
        "templates/routine-trader/.env.example",
        "templates/routine-trader/.gitignore",
        "templates/routine-trader/configs/market.example.yaml",
        "templates/routine-trader/memory/portfolio.md",
        "templates/routine-trader/routines/prompts/pre_market.md",
        "templates/routine-trader/skills/risk_review.md",
    ):
        zf.writestr(f"atlas_agent/{rel}", f"test resource: {rel}\n")


def _make_fake_sdist(
    path: Path,
    name: str = "atlas-agent",
    version: str = PACKAGE_VERSION,
    include_templates: bool = False,
) -> None:
    """Create a minimal fake sdist with PKG-INFO."""
    pkg_info = (
        f"Metadata-Version: 2.1\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        f"Summary: Atlas Agent test sdist\n"
    )
    with tarfile.open(path, "w:gz") as tf:
        info = tarfile.TarInfo(name="PKG-INFO")
        data = pkg_info.encode("utf-8")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        if include_templates:
            for rel in (
                "templates/routine-trader/README.md",
                "templates/routine-trader/.env.example",
                "templates/routine-trader/.gitignore",
                "templates/routine-trader/configs/market.example.yaml",
                "templates/routine-trader/memory/portfolio.md",
                "templates/routine-trader/routines/prompts/pre_market.md",
                "templates/routine-trader/skills/risk_review.md",
            ):
                member = tarfile.TarInfo(name=f"atlas-agent-{version}/src/atlas_agent/{rel}")
                data = f"test resource: {rel}\n".encode("utf-8")
                member.size = len(data)
                tf.addfile(member, io.BytesIO(data))


# ---------------------------------------------------------------------------
# Script existence and structure
# ---------------------------------------------------------------------------


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

    def test_no_shell_true(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "shell=True" not in text, "Script must not use shell=True"

    def test_no_credential_loading(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "load_dotenv" not in text
        assert "api_key" not in text

    def test_no_broker_or_provider_calls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "place_order" not in text
        assert "resolve_execution_broker" not in text
        assert "broker.submit" not in text

    def test_no_publish_or_upload(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "twine upload" not in text
        assert "gh release create" not in text
        assert "git push" not in text
        assert "git tag -a" not in text
        # The docstring and comments may mention pypi/upload as things NOT done.
        # Verify no actual publish/upload command patterns exist.
        assert "subprocess.run" not in text or "twine upload" not in text
        assert "subprocess.run" not in text or "gh release" not in text

    def test_default_build_uses_no_isolation(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert '"--no-isolation"' in text, "Default build must use --no-isolation"

    def test_no_silent_network_fallback(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        assert "retry" not in text or "with network" not in text
        assert "allow_network_build" in text or "no-isolation" in text

    def test_failure_output_is_redacted_before_print(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        # The _build_artifacts function must call _redact on stdout/stderr
        # before returning the error message.
        build_fn_start = text.find("def _build_artifacts(")
        build_fn_end = text.find("def _find_artifacts(")
        build_fn = text[build_fn_start:build_fn_end]
        assert "_redact(stdout)" in build_fn or "_redact" in build_fn, (
            "Build failure output must be redacted before returning"
        )

    def test_dry_run_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--dry-run" in text

    def test_keep_artifacts_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--keep-artifacts" in text

    def test_output_dir_flag_exists(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert "--output-dir" in text


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_exits_zero(self) -> None:
        result = _run_script("--dry-run")
        assert result.returncode == 0, f"dry-run failed:\n{result.stdout}\n{result.stderr}"

    def test_dry_run_shows_plan(self) -> None:
        result = _run_script("--dry-run")
        assert "Package distribution verification plan" in result.stdout
        assert "verify wheel exists" in result.stdout
        assert "verify sdist exists" in result.stdout
        assert "verify wheel contains packaged routine-trader templates" in result.stdout
        assert "verify sdist contains packaged routine-trader templates" in result.stdout
        assert "run atlas init outside repo" in result.stdout

    def test_dry_run_does_not_create_artifacts(self, tmp_path: Path) -> None:
        result = _run_script("--dry-run", cwd=tmp_path)
        assert result.returncode == 0
        assert not list(tmp_path.glob("atlas-dist-check-*"))


# ---------------------------------------------------------------------------
# Version expectations
# ---------------------------------------------------------------------------


class TestVersionReporting:
    def test_expected_version_matches_pyproject(self) -> None:
        import tomllib
        pyproject = REPO_ROOT / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        pkg_version = data.get("project", {}).get("version")
        text = SCRIPT.read_text(encoding="utf-8")
        assert f'EXPECTED_PACKAGE_VERSION = "{pkg_version}"' in text

    def test_expected_tag_matches_version(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        assert 'EXPECTED_PUBLIC_TAG = "v0.5.8.1"' in text


# ---------------------------------------------------------------------------
# Path redaction
# ---------------------------------------------------------------------------


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

    def test_redaction_of_forbidden_paths(self, monkeypatch) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_test", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_test"] = cpd
        spec.loader.exec_module(cpd)
        monkeypatch.setattr(cpd, "_CURRENT_TEMP_DIR", "/var/folders/abc/T/tmp123")
        sample = (
            "Error in /Users/testuser/Desktop/repo "
            "and /private/var/folders/abc/T/tmp123 "
            "and /var/folders/abc/T/tmp456 "
            "and /tmp/secret "
            "and /var/tmp/secret"
        )
        redacted = cpd._redact(sample)
        assert "/Users/" not in redacted
        assert "/private/var/" not in redacted
        assert "/var/folders/" not in redacted
        assert "/tmp/" not in redacted
        assert "/var/tmp/" not in redacted
        assert "<temp>" in redacted or "~" in redacted


# ---------------------------------------------------------------------------
# Wheel metadata parser (fake wheels)
# ---------------------------------------------------------------------------


class TestWheelMetadataParser:
    def test_parses_correct_wheel(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_wheel", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_wheel"] = cpd
        spec.loader.exec_module(cpd)

        wheel_path = tmp_path / f"atlas_agent-{CURRENT_PACKAGE_VERSION}-py3-none-any.whl"
        _make_fake_wheel(wheel_path, name="atlas_agent", version=CURRENT_PACKAGE_VERSION)
        ok, errors = cpd._check_wheel_metadata(wheel_path)
        assert ok, f"Unexpected errors: {errors}"
        assert errors == []

    def test_rejects_wrong_version(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_wheel2", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_wheel2"] = cpd
        spec.loader.exec_module(cpd)

        wheel_path = tmp_path / "atlas_agent-0.5.7rc7-py3-none-any.whl"
        _make_fake_wheel(wheel_path, name="atlas_agent", version="0.5.7rc3")
        ok, errors = cpd._check_wheel_metadata(wheel_path)
        assert not ok
        assert any("0.5.7rc3" in e for e in errors)

    def test_rejects_missing_entry_point(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_wheel3", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_wheel3"] = cpd
        spec.loader.exec_module(cpd)

        wheel_path = tmp_path / "atlas_agent-0.5.7rc3-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            metadata = (
                "Metadata-Version: 2.1\n"
                "Name: atlas_agent\n"
                "Version: 0.5.7rc3\n"
            )
            zf.writestr("atlas_agent-0.0.0.dist-info/METADATA", metadata)
            # No entry_points.txt
        ok, errors = cpd._check_wheel_metadata(wheel_path)
        assert not ok
        assert any("entry_points" in e.lower() for e in errors)

    def test_rejects_forbidden_claim_in_metadata(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_wheel4", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_wheel4"] = cpd
        spec.loader.exec_module(cpd)

        wheel_path = tmp_path / "atlas_agent-0.5.7rc3-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            metadata = (
                "Metadata-Version: 2.1\n"
                "Name: atlas_agent\n"
                "Version: 0.5.7rc3\n"
                "Description: This package is live trading ready\n"
            )
            zf.writestr("atlas_agent-0.0.0.dist-info/METADATA", metadata)
            zf.writestr(
                "atlas_agent-0.0.0.dist-info/entry_points.txt",
                "[console_scripts]\natlas = atlas_agent.cli:main\n",
            )
        ok, errors = cpd._check_wheel_metadata(wheel_path)
        assert not ok
        assert any("live trading ready" in e.lower() for e in errors)


class TestWheelTemplateParser:
    def test_parses_wheel_templates(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_wheel_templates", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_wheel_templates"] = cpd
        spec.loader.exec_module(cpd)

        wheel_path = tmp_path / f"atlas_agent-{CURRENT_PACKAGE_VERSION}-py3-none-any.whl"
        _make_fake_wheel(wheel_path, name="atlas_agent", version=CURRENT_PACKAGE_VERSION)
        with zipfile.ZipFile(wheel_path, "a") as zf:
            _write_fake_wheel_templates(zf)
        ok, errors = cpd._check_wheel_templates(wheel_path)
        assert ok, f"Unexpected errors: {errors}"

    def test_rejects_wheel_missing_templates(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_wheel_templates_missing", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_wheel_templates_missing"] = cpd
        spec.loader.exec_module(cpd)

        wheel_path = tmp_path / f"atlas_agent-{CURRENT_PACKAGE_VERSION}-py3-none-any.whl"
        _make_fake_wheel(wheel_path, name="atlas_agent", version=CURRENT_PACKAGE_VERSION)
        ok, errors = cpd._check_wheel_templates(wheel_path)
        assert not ok
        assert any("Template file missing from wheel" in e for e in errors)


# ---------------------------------------------------------------------------
# Sdist metadata parser (fake sdists)
# ---------------------------------------------------------------------------


class TestSdistMetadataParser:
    def test_parses_correct_sdist(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_sdist", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_sdist"] = cpd
        spec.loader.exec_module(cpd)

        sdist_path = tmp_path / f"atlas-agent-{CURRENT_PACKAGE_VERSION}.tar.gz"
        _make_fake_sdist(sdist_path, name="atlas-agent", version=CURRENT_PACKAGE_VERSION)
        ok, errors = cpd._check_sdist_metadata(sdist_path)
        assert ok, f"Unexpected errors: {errors}"
        assert errors == []

    def test_rejects_wrong_version(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_sdist2", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_sdist2"] = cpd
        spec.loader.exec_module(cpd)

        sdist_path = tmp_path / "atlas-agent-0.5.7rc7.tar.gz"
        _make_fake_sdist(sdist_path, name="atlas-agent", version="0.5.7rc3")
        ok, errors = cpd._check_sdist_metadata(sdist_path)
        assert not ok
        assert any("0.5.7rc3" in e for e in errors)

    def test_rejects_forbidden_claim_in_pkg_info(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_sdist3", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_sdist3"] = cpd
        spec.loader.exec_module(cpd)

        sdist_path = tmp_path / "atlas-agent-0.5.7rc3.tar.gz"
        pkg_info = (
            "Metadata-Version: 2.1\n"
            "Name: atlas-agent\n"
            "Version: 0.5.7rc3\n"
            "Description: This strategy guaranteed profit\n"
        )
        with tarfile.open(sdist_path, "w:gz") as tf:
            info = tarfile.TarInfo(name="PKG-INFO")
            data = pkg_info.encode("utf-8")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        ok, errors = cpd._check_sdist_metadata(sdist_path)
        assert not ok
        assert any("guaranteed profit" in e.lower() for e in errors)


class TestSdistTemplateParser:
    def test_parses_sdist_templates(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_sdist_templates", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_sdist_templates"] = cpd
        spec.loader.exec_module(cpd)

        sdist_path = tmp_path / f"atlas-agent-{CURRENT_PACKAGE_VERSION}.tar.gz"
        _make_fake_sdist(
            sdist_path,
            name="atlas-agent",
            version=CURRENT_PACKAGE_VERSION,
            include_templates=True,
        )
        ok, errors = cpd._check_sdist_templates(sdist_path)
        assert ok, f"Unexpected errors: {errors}"

    def test_rejects_sdist_missing_templates(self, tmp_path: Path) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_sdist_templates_missing", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_sdist_templates_missing"] = cpd
        spec.loader.exec_module(cpd)

        sdist_path = tmp_path / f"atlas-agent-{CURRENT_PACKAGE_VERSION}.tar.gz"
        _make_fake_sdist(sdist_path, name="atlas-agent", version=CURRENT_PACKAGE_VERSION)
        ok, errors = cpd._check_sdist_templates(sdist_path)
        assert not ok
        assert any("Template file missing from sdist" in e for e in errors)


# ---------------------------------------------------------------------------
# Artifact filename checks
# ---------------------------------------------------------------------------


class TestArtifactFilenameChecks:
    def test_correct_filenames_pass(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_fn", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_fn"] = cpd
        spec.loader.exec_module(cpd)

        wheel = Path(f"atlas_agent-{CURRENT_PACKAGE_VERSION}-py3-none-any.whl")
        sdist = Path(f"atlas-agent-{CURRENT_PACKAGE_VERSION}.tar.gz")
        errors = cpd._check_artifact_filenames(wheel, sdist)
        assert errors == []

    def test_wrong_version_fails(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_fn2", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_fn2"] = cpd
        spec.loader.exec_module(cpd)

        wheel = Path("atlas_agent-0.5.6-py3-none-any.whl")
        sdist = Path("atlas-agent-0.5.6.tar.gz")
        errors = cpd._check_artifact_filenames(wheel, sdist)
        assert len(errors) == 2


# ---------------------------------------------------------------------------
# Real build (if build module available)
# ---------------------------------------------------------------------------


class TestRealBuild:
    def test_real_build_passes(self) -> None:
        result = _run_script()
        if result.returncode == 2 and "build missing" in (result.stdout + result.stderr).lower():
            pytest.skip("build module not available")
        assert result.returncode == 0, (
            f"Package distribution check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "Package distribution verification PASSED" in result.stdout
        assert f"Package version: {CURRENT_PACKAGE_VERSION}" in result.stdout
        assert "Template resources checked: yes" in result.stdout
        assert "Wheel-installed template init checked: yes" in result.stdout
        assert "Build isolation: disabled" in result.stdout or "Network allowed: False" in result.stdout

    def test_real_build_output_has_no_absolute_paths(self) -> None:
        result = _run_script()
        if result.returncode != 0 and "build missing" in (result.stdout + result.stderr).lower():
            pytest.skip("build module not available")
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "/Users/" not in combined, f"Leaked /Users/ in output:\n{combined}"
        assert "/private/var/" not in combined
        assert "/var/folders/" not in combined
        assert "/tmp/" not in combined
        assert "/var/tmp/" not in combined


# ---------------------------------------------------------------------------
# Safety claims
# ---------------------------------------------------------------------------


class TestFailedBuildRedaction:
    def test_build_failure_stdout_stderr_redacted(self, monkeypatch, tmp_path, capsys):
        """Simulate failed build subprocess with forbidden paths in stdout/stderr.

        Assert the final output/report does NOT contain raw absolute paths
        and instead contains safe placeholders (<temp>, ~, <repo>, <users>).
        """
        import importlib.util
        import tempfile as _tempfile_module

        spec = importlib.util.spec_from_file_location(
            "check_package_distribution_failure", str(SCRIPT)
        )
        cpd = importlib.util.module_from_spec(spec)
        sys.modules["check_package_distribution_failure"] = cpd
        spec.loader.exec_module(cpd)

        fake_output = tmp_path / "atlas-dist-check-test"
        fake_output.mkdir()

        def _fake_mkdtemp(prefix="", dir=None):
            return str(fake_output)

        monkeypatch.setattr(_tempfile_module, "mkdtemp", _fake_mkdtemp)

        home = str(Path.home())
        repo = str(cpd.REPO_ROOT)

        def fake_run(cmd, **kwargs):
            if "-m" in cmd and "build" in cmd:
                stderr = (
                    f"Could not build in {fake_output}/build\n"
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

        monkeypatch.setattr(cpd, "_run", fake_run)
        # Also pretend build is available so we reach the build step
        monkeypatch.setattr(cpd, "_check_build_available", lambda: (True, ""))

        ret = cpd.main([])

        captured = capsys.readouterr()
        combined = captured.out + captured.err

        assert ret == 2, f"Expected exit code 2, got {ret}"
        assert "Build failed" in combined or "ERROR:" in combined

        # No raw forbidden paths
        assert "/Users/" not in combined, f"Leaked /Users/ in output:\n{combined}"
        assert "/private/var/" not in combined
        assert "/var/folders/" not in combined
        assert "/tmp/" not in combined
        assert "/var/tmp/" not in combined
        assert str(fake_output) not in combined
        assert home not in combined
        assert repo not in combined

        # Safe placeholders present
        assert "<temp>" in combined or "<users>" in combined
        if home != "/":
            assert "~" in combined, f"Home path not redacted with ~:\n{combined}"


class TestSafetyClaims:
    def test_no_live_trading_ready_claims(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        # The script contains a FORBIDDEN_METADATA_CLAIMS denylist that includes
        # this phrase; it is allowed only in that negative-scanning context.
        lines = text.splitlines()
        in_denylist = False
        for line in lines:
            if "forbidden_metadata_claims" in line:
                in_denylist = True
            if in_denylist and line.strip() == "]":
                in_denylist = False
            if not in_denylist and "live trading ready" in line:
                pytest.fail(f"Forbidden positive claim outside denylist: {line}")

    def test_no_profitability_claims(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8").lower()
        lines = text.splitlines()
        in_denylist = False
        for line in lines:
            if "forbidden_metadata_claims" in line:
                in_denylist = True
            if in_denylist and line.strip() == "]":
                in_denylist = False
            if not in_denylist:
                if "guaranteed profit" in line or "profitable strategy" in line:
                    pytest.fail(f"Forbidden positive claim outside denylist: {line}")
