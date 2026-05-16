from __future__ import annotations


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _lower(text: str) -> str:
    return text.lower()


def _assert_absent_outside_negative_context(text: str, phrase: str) -> bool:
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
    )
    return any(ind in context for ind in negative_indicators)


class TestReferenceDocExists:
    def test_file_exists(self) -> None:
        text = _read("docs/research-workflow.md")
        assert text.strip()


class TestReferenceDocCommands:
    def test_mentions_run_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research run" in text.lower()

    def test_mentions_list_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research list" in text.lower()

    def test_mentions_show_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research show" in text.lower()

    def test_mentions_plan_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research plan" in text.lower()

    def test_mentions_verify_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research verify" in text.lower()

    def test_mentions_evaluate_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research evaluate" in text.lower()

    def test_mentions_summary_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research summary" in text.lower()

    def test_mentions_check_artifacts_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research check-artifacts" in text.lower()

    def test_mentions_timeline_command(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "atlas research timeline" in text.lower()

    def test_mentions_timeline_read_only(self) -> None:
        text = _read("docs/research-workflow.md")
        lower_text = text.lower()
        assert "timeline" in lower_text
        assert "read-only" in lower_text or "read_only" in lower_text or "read only" in lower_text

    def test_mentions_lineage_or_relationship(self) -> None:
        text = _read("docs/research-workflow.md")
        lower_text = text.lower()
        assert "lineage" in lower_text or "relationship" in lower_text or "linking" in lower_text or "descendants" in lower_text

    def test_mentions_demo_script(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "scripts/demo_research_workflow.sh" in text


class TestReferenceDocArtifactPaths:
    def test_research_artifact_path(self) -> None:
        text = _read("docs/research-workflow.md")
        assert ".atlas/research/<SYMBOL>/<run_id>.json" in text

    def test_plan_artifact_path(self) -> None:
        text = _read("docs/research-workflow.md")
        assert ".atlas/research/<SYMBOL>/plans/<plan_id>.json" in text

    def test_verification_artifact_path(self) -> None:
        text = _read("docs/research-workflow.md")
        assert ".atlas/research/<SYMBOL>/verifications/<verification_id>.json" in text

    def test_evaluation_artifact_path(self) -> None:
        text = _read("docs/research-workflow.md")
        assert ".atlas/research/<SYMBOL>/evaluations/<evaluation_id>.json" in text


class TestReferenceDocSafetyBoundaries:
    def test_does_not_submit_orders(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "does not submit orders" in text.lower()

    def test_does_not_create_approvals(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "does not create approvals" in text.lower()

    def test_does_not_create_pending_orders(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "does not create pending orders" in text.lower()

    def test_does_not_authorize_live_trading(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "does not authorize live trading" in text.lower()

    def test_does_not_call_brokers(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "does not call brokers" in text.lower()

    def test_does_not_require_broker_credentials(self) -> None:
        text = _read("docs/research-workflow.md")
        assert "does not require broker credentials" in text.lower()


class TestReferenceDocReadOnlyCommands:
    def test_list_is_read_only(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "list" in lower and "read-only" in lower

    def test_show_is_read_only(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "show" in lower and "read-only" in lower

    def test_summary_is_read_only(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "summary" in lower and "read-only" in lower


class TestReferenceDocEvaluationLimitations:
    def test_does_not_produce_trading_signals(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "does not produce trading signals" in lower

    def test_does_not_estimate_profit(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "does not estimate profit" in lower

    def test_uses_local_csv_data(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "local csv" in lower or "local csv data" in lower


class TestReferenceDocForbiddenClaims:
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

    def test_no_forbidden_claims(self) -> None:
        text = _read("docs/research-workflow.md")
        failures = []
        for phrase in self.FORBIDDEN:
            if not _assert_absent_outside_negative_context(text, phrase):
                failures.append(phrase)
        assert not failures, f"Forbidden claims in docs/research-workflow.md: {failures}"


class TestReferenceDocSchemaVersioning:
    def test_schema_version_mentioned(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "schema_version" in lower
        assert "current schema version" in lower

    def test_legacy_compat_mentioned(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "legacy" in lower or "older artifacts" in lower

    def test_no_rewrite_claim(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "does not silently rewrite" in lower or "does not rewrite" in lower


class TestReferenceDocCheckArtifacts:
    def test_check_artifacts_read_only(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "check-artifacts" in lower and "read-only" in lower

    def test_check_artifacts_no_migration(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "does not modify" in lower or "does not migrate" in lower or "does not rewrite" in lower

    def test_check_artifacts_detects_issues(self) -> None:
        text = _read("docs/research-workflow.md")
        lower = text.lower()
        assert "malformed" in lower or "duplicate" in lower or "schema" in lower


class TestReadmeLinksToReferenceDoc:
    def test_readme_links_to_research_workflow_md(self) -> None:
        text = _read("README.md")
        assert "docs/research-workflow.md" in text
