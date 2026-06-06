"""Tests for provider policy docs — Batch 8.0.

This batch is documentation/policy/test-only. No provider execution code,
no network calls, no credentials, no provider SDKs, no broker changes.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _lower(text: str) -> str:
    return text.lower()


def _assert_absent_outside_negative_context(text: str, phrase: str) -> bool:
    """Return True if phrase is absent or only appears in a negative/disclaimer context."""
    lower_text = text.lower()
    phrase_lower = phrase.lower()
    idx = lower_text.find(phrase_lower)
    if idx == -1:
        return True
    window = 120
    start = max(0, idx - window)
    end = min(len(text), idx + len(phrase_lower) + window)
    context = lower_text[start:end]
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
    )
    return any(ind in context for ind in negative_indicators)


# ---------------------------------------------------------------------------
# Doc existence
# ---------------------------------------------------------------------------

class TestPolicyDocsExist:
    def test_threat_model_exists(self) -> None:
        text = _read("docs/security/provider-integration-threat-model.md")
        assert text.strip()

    def test_execution_policy_exists(self) -> None:
        text = _read("docs/security/provider-execution-policy.md")
        assert text.strip()

    def test_integration_requirements_exists(self) -> None:
        text = _read("docs/security/provider-integration-requirements.md")
        assert text.strip()

    def test_adr_exists(self) -> None:
        text = _read("docs/adr/ADR-0001-provider-execution-boundary.md")
        assert text.strip()

    def test_release_notes_exist(self) -> None:
        text = _read("docs/releases/v0.5.7.dev27.md")
        assert text.strip()


# ---------------------------------------------------------------------------
# Forbidden overclaims (must be absent or in negative context)
# ---------------------------------------------------------------------------

class TestPolicyDocsNoForbiddenOverclaims:
    def _check_all_docs(self, phrase: str) -> None:
        docs = [
            "docs/security/provider-integration-threat-model.md",
            "docs/security/provider-execution-policy.md",
            "docs/security/provider-integration-requirements.md",
            "docs/adr/ADR-0001-provider-execution-boundary.md",
            "docs/releases/v0.5.7.dev27.md",
            "README.md",
            "CHANGELOG.md",
        ]
        for path in docs:
            text = _read(path)
            assert _assert_absent_outside_negative_context(
                text, phrase
            ), f"Forbidden overclaim '{phrase}' found outside negative context in {path}"

    def test_no_production_ready_provider_execution(self) -> None:
        self._check_all_docs("production-ready provider execution")

    def test_no_live_trading_ready(self) -> None:
        self._check_all_docs("live trading ready")

    def test_no_provider_calls_enabled(self) -> None:
        self._check_all_docs("provider calls enabled")

    def test_no_api_support_enabled(self) -> None:
        self._check_all_docs("api support enabled")

    def test_no_approved_to_trade(self) -> None:
        self._check_all_docs("approved to trade")

    def test_no_authorized_to_execute(self) -> None:
        self._check_all_docs("authorized to execute")

    def test_no_trading_signal(self) -> None:
        self._check_all_docs("trading signal")


# ---------------------------------------------------------------------------
# Required safety claims (must be present)
# ---------------------------------------------------------------------------

class TestPolicyDocsContainRequiredSafetyClaims:
    def _check_doc_contains(self, path: str, phrase: str) -> None:
        text = _read(path)
        assert phrase.lower() in text.lower(), f"Required safety claim '{phrase}' missing from {path}"

    def test_threat_model_no_provider_call(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-integration-threat-model.md", "no provider call is made"
        )

    def test_threat_model_no_api_keys(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-integration-threat-model.md", "no api keys are read"
        )

    def test_threat_model_no_network(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-integration-threat-model.md", "no network is used"
        )

    def test_threat_model_no_provider_sdks(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-integration-threat-model.md", "no provider sdks are imported"
        )

    def test_threat_model_no_broker(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-integration-threat-model.md", "no broker is touched"
        )

    def test_policy_no_approvals_orders(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-execution-policy.md", "no approvals or pending orders are created"
        )

    def test_adr_no_provider_calls_today(self) -> None:
        self._check_doc_contains(
            "docs/adr/ADR-0001-provider-execution-boundary.md", "does not authorize real provider calls today"
        )

    def test_release_notes_no_real_provider(self) -> None:
        self._check_doc_contains(
            "docs/releases/v0.5.7.dev27.md", "no real provider execution added"
        )

    def test_requirements_future_opt_in(self) -> None:
        self._check_doc_contains(
            "docs/security/provider-integration-requirements.md", "future opt-in"
        )


# ---------------------------------------------------------------------------
# Docs-only / no-provider-code assertions
# ---------------------------------------------------------------------------

class TestBatch8NoProviderCode:
    """Confirm this batch did not introduce provider execution code."""

    def _scan_source_for_import(self, module_name: str) -> list[str]:
        repo_root = Path(__file__).resolve().parent.parent / "src" / "atlas_agent"
        findings: list[str] = []
        for path in repo_root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == module_name or alias.name.startswith(f"{module_name}."):
                            findings.append(str(path.relative_to(repo_root)))
                elif isinstance(node, ast.ImportFrom):
                    if node.module == module_name or (
                        node.module and node.module.startswith(f"{module_name}.")
                    ):
                        findings.append(str(path.relative_to(repo_root)))
        return findings

    def test_no_openai_import(self) -> None:
        assert self._scan_source_for_import("openai") == []

    def test_no_anthropic_import(self) -> None:
        assert self._scan_source_for_import("anthropic") == []

    def test_no_openrouter_import(self) -> None:
        assert self._scan_source_for_import("openrouter") == []

    def test_no_moonshot_import(self) -> None:
        assert self._scan_source_for_import("moonshot") == []

    def test_no_kimi_import(self) -> None:
        assert self._scan_source_for_import("kimi") == []

    def test_no_httpx_import(self) -> None:
        assert self._scan_source_for_import("httpx") == []

    def test_no_requests_import(self) -> None:
        assert self._scan_source_for_import("requests") == []

    def test_no_urllib_provider_call(self) -> None:
        # urllib is used elsewhere for non-provider things; check urllib.request.urlopen specifically
        repo_root = Path(__file__).resolve().parent.parent / "src" / "atlas_agent"
        findings: list[str] = []
        for path in repo_root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "urllib.request.urlopen" in text or "urllib.request.Request" in text:
                findings.append(str(path.relative_to(repo_root)))
        # Pre-existing files with urllib usage are allowed; this batch must not add new ones
        allowed = {
            "cli.py",
            "research/perplexity.py",
            "brokers/alpaca.py",
            "update/sources.py",
            "providers/openai_compatible.py",
            "notifications/clickup.py",
            # notifications/transports.py contains a Slack webhook transport
            # that uses urllib.request for POST calls. This is NOT provider
            # execution; it is a notification transport. It is disabled/dry-run
            # by default, requires explicit slack transport configuration, and
            # tests use injected/mocked http_post with no real network.
            "notifications/transports.py",
        }
        unexpected = [f for f in findings if f not in allowed]
        assert unexpected == [], f"Unexpected urllib network usage in: {unexpected}"

    def test_no_authorization_header_in_source(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent / "src" / "atlas_agent"
        findings: list[str] = []
        for path in repo_root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "Authorization" in text:
                findings.append(str(path.relative_to(repo_root)))
        # Authorization may appear in forbidden-fragments constants or denylist checks
        # Allowlist known safe occurrences in pre-existing files
        allowed = {
            "research/sandbox_contracts.py",  # FORBIDDEN_FRAGMENTS contains "Authorization"
            "research/provider_preflight_freeze.py",  # uses FORBIDDEN_FRAGMENTS
            "research/provider_execution_readiness_report.py",
            "research/provider_execution_audit_packet.py",
            "research/provider_execution_state.py",
            "research/provider_execution_dry_run.py",
            "research/provider_call_plan.py",
            "research/session.py",
            "research/perplexity.py",
            "research/release_candidate_cutover.py",  # uses FORBIDDEN_FRAGMENTS
            "providers/openai_compatible.py",
            "setup/wizard_ui.py",
            "notifications/clickup.py",
            "cli.py",  # may reference forbidden fragments in error mapping
        }
        unexpected = [f for f in findings if f not in allowed]
        assert unexpected == [], f"Unexpected Authorization usage in: {unexpected}"

    def test_no_new_provider_execution_module_beyond_preflight(self) -> None:
        """Ensure no new executable provider adapter modules were added."""
        repo_root = Path(__file__).resolve().parent.parent / "src" / "atlas_agent"
        # The preflight modules are expected; any *adapter* or *client* module is not
        disallowed_patterns = [
            "*provider_adapter*",
            "*provider_client*",
            "*llm_client*",
            "*api_client*",
        ]
        # Interface-only disabled-harness modules are explicitly allowed
        allowed_interface_only = {
            "research/provider_adapter_interface.py",
            "research/provider_adapter_interface_contract.py",
        }
        findings: list[str] = []
        for pattern in disallowed_patterns:
            for path in repo_root.rglob(pattern):
                if path.is_file() and "__pycache__" not in str(path):
                    rel = str(path.relative_to(repo_root))
                    if rel not in allowed_interface_only:
                        findings.append(rel)
        assert findings == [], f"Unexpected provider adapter/client modules: {findings}"

    def test_allowed_adapter_interface_modules_are_safe(self) -> None:
        """Ensure allowed interface-only adapter modules do not import SDKs, HTTP clients, or env."""
        repo_root = Path(__file__).resolve().parent.parent / "src" / "atlas_agent"
        allowed_modules = [
            repo_root / "research" / "provider_adapter_interface.py",
            repo_root / "research" / "provider_adapter_interface_contract.py",
        ]
        forbidden_imports = ["openai", "anthropic", "openrouter", "moonshot", "kimi", "httpx", "requests", "urllib3"]
        for module_path in allowed_modules:
            text = module_path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_imports:
                            imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module in forbidden_imports:
                        imports.append(node.module)
            assert imports == [], f"Forbidden SDK/HTTP import in {module_path.name}: {imports}"
            # Check for os.environ / os.getenv / load_dotenv via AST (not string match, to avoid docstring false positives)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr in ("environ", "getenv"):
                        assert False, f"Forbidden env access os.{node.attr} in {module_path.name}"
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "load_dotenv":
                        assert False, f"Forbidden load_dotenv call in {module_path.name}"
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr == "load_dotenv":
                            assert False, f"Forbidden load_dotenv call in {module_path.name}"
            # Check for urllib network calls in actual code (not docstrings)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if node.attr in ("urlopen", "Request"):
                        assert False, f"Forbidden urllib network call in {module_path.name}"
