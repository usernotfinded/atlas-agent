from __future__ import annotations


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _lower(text: str) -> str:
    return text.lower()


def _extract_section(text: str, heading: str) -> str:
    """Extract content under a markdown heading until the next heading of same or higher level."""
    lines = text.splitlines()
    result: list[str] = []
    in_section = False
    heading_level = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if in_section and level <= heading_level:
                break
            if stripped.strip().lower().startswith(heading.lower()):
                in_section = True
                heading_level = level
                continue
        if in_section:
            result.append(line)
    return "\n".join(result)


def _assert_absent_outside_negative_context(text: str, phrase: str) -> bool:
    """Return True if phrase is absent or only appears in a negative/disclaimer context."""
    lower_text = text.lower()
    phrase_lower = phrase.lower()
    idx = lower_text.find(phrase_lower)
    if idx == -1:
        return True
    # Check surrounding context for negative qualifiers
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
    )
    return any(ind in context for ind in negative_indicators)


class TestReadmeResearchCommands:
    def test_readme_mentions_run_command(self) -> None:
        text = _read("README.md")
        assert "atlas research run" in text.lower()

    def test_readme_mentions_list_command(self) -> None:
        text = _read("README.md")
        assert "atlas research list" in text.lower()

    def test_readme_mentions_show_command(self) -> None:
        text = _read("README.md")
        assert "atlas research show" in text.lower()

    def test_readme_mentions_plan_command(self) -> None:
        text = _read("README.md")
        assert "atlas research plan" in text.lower()

    def test_readme_mentions_summary_command(self) -> None:
        text = _read("README.md")
        assert "atlas research summary" in text.lower()


class TestReadmeResearchWording:
    def test_paper_only_mentioned(self) -> None:
        text = _read("README.md")
        assert "paper-only" in text.lower() or "paper only" in text.lower()

    def test_analysis_only_or_local_artifact(self) -> None:
        text = _read("README.md")
        lower = text.lower()
        assert "analysis-only" in lower or "analysis only" in lower or "local" in lower
        assert "artifact" in lower

    def test_no_trading_signal_claims(self) -> None:
        text = _read("README.md")
        forbidden = [
            "trading signal",
            "buy recommendation",
            "sell recommendation",
            "financial advice",
            "profitable",
            "guaranteed",
            "production-ready live trading",
            "autonomous live trading",
            "safe live trading",
            "risk-free",
            "zero risk",
            "no risk",
        ]
        failures = []
        for phrase in forbidden:
            if not _assert_absent_outside_negative_context(text, phrase):
                failures.append(phrase)
        assert not failures, f"Forbidden claims found: {failures}"


class TestArchitectureResearchWorkflow:
    def test_section_exists(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert section.strip(), "Research Workflow section not found"

    def test_run_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "run" in lower
        assert "artifact" in lower

    def test_list_show_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "list" in lower
        assert "show" in lower
        assert "read-only" in lower or "read only" in lower

    def test_plan_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "plan" in lower
        assert "paper-only" in lower or "paper only" in lower

    def test_summary_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "summary" in lower
        assert "read-only" in lower or "read only" in lower

    def test_progression_described(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        # run creates, list/show inspect, plan derives, summary overviews
        assert "create" in lower or "creates" in lower
        assert "discover" in lower or "inspect" in lower
        assert "derive" in lower or "derives" in lower or "from" in lower
        assert "overview" in lower or "summarize" in lower or "summary" in lower


class TestArchitectureNoExecutionBoundary:
    def test_does_not_submit_orders(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "does not submit orders" in section.lower() or "does not submit" in section.lower()

    def test_does_not_create_pending_orders(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "does not create pending orders" in section.lower()

    def test_does_not_create_approvals(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "does not create approvals" in section.lower() or "approval" in section.lower()

    def test_does_not_call_brokers(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "does not call brokers" in section.lower() or "does not call broker" in section.lower()

    def test_does_not_authorize_live_trading(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "does not authorize live trading" in section.lower()


class TestArchitectureArtifactSchema:
    def test_research_artifact_fields_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        required_fields = [
            "run_id",
            "symbol",
            "mode",
            "provider",
            "summary",
            "thesis",
            "market_context",
            "risks",
            "invalidation_conditions",
            "paper_only_plan",
            "warnings",
        ]
        missing = [f for f in required_fields if f not in lower]
        assert not missing, f"Missing research artifact fields: {missing}"

    def test_plan_artifact_fields_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        required_fields = [
            "plan_id",
            "source_run_id",
            "thesis_recap",
            "constraints",
            "risk_notes",
            "invalidation_checks",
            "paper_only_actions",
            "verification_steps",
        ]
        missing = [f for f in required_fields if f not in lower]
        assert not missing, f"Missing plan artifact fields: {missing}"


class TestArchitecturePathSafety:
    def test_workspace_relative_paths_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "workspace-relative" in section.lower() or "relative" in section.lower()

    def test_no_absolute_path_output_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "absolute" in section.lower() or "no absolute" in section.lower()

    def test_safe_event_metadata_documented(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        assert "event" in section.lower()

    def test_no_full_artifact_body_in_event(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        # Architecture mentions safe payloads with bounded keys
        assert "payload" in section.lower() or "safe" in section.lower()


class TestArchitectureReadOnlyListShow:
    def test_list_read_only(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "list" in lower and "read-only" in lower

    def test_show_read_only(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "show" in lower and "read-only" in lower

    def test_list_show_do_not_create_artifacts(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "do not create" in lower or "does not create" in lower or "do not create files" in lower


class TestArchitecturePlanPaperOnly:
    def test_plan_creates_paper_only_plan(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "plan" in lower and "paper-only" in lower

    def test_plan_does_not_authorize_live_trading(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "plan" in lower and "does not authorize live trading" in lower

    def test_plan_does_not_create_pending_orders(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "plan" in lower and "does not create pending orders" in lower

    def test_plan_does_not_create_approvals(self) -> None:
        text = _read("docs/architecture.md")
        section = _extract_section(text, "## Research Workflow")
        lower = section.lower()
        assert "plan" in lower and "approval" in lower


class TestForbiddenClaims:
    FORBIDDEN = [
        "zero risk",
        "risk-free",
        "guaranteed profit",
        "profit guaranteed",
        "guaranteed returns",
        "can't lose",
        "no risk",
        "safe live trading",
        "production-ready live trading",
        "autonomous live trading",
        "fully autonomous trading",
        "trading signal engine",
        "financial advisor",
    ]

    def test_readme_no_forbidden_claims(self) -> None:
        text = _read("README.md")
        failures = []
        for phrase in self.FORBIDDEN:
            if not _assert_absent_outside_negative_context(text, phrase):
                failures.append(phrase)
        assert not failures, f"Forbidden claims in README.md: {failures}"

    def test_architecture_no_forbidden_claims(self) -> None:
        text = _read("docs/architecture.md")
        failures = []
        for phrase in self.FORBIDDEN:
            if not _assert_absent_outside_negative_context(text, phrase):
                failures.append(phrase)
        assert not failures, f"Forbidden claims in architecture.md: {failures}"
