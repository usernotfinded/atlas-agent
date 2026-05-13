from __future__ import annotations

from pathlib import Path
import re


ROUTINES = (
    "pre_market",
    "market_open",
    "midday_scan",
    "market_close",
    "weekly_review",
)
ENV_NAMES = (
    "TRADING_MODE",
    "ENABLE_LIVE_TRADING",
    "LIVE_BROKER",
    "ORDER_APPROVAL_MODE",
    "KILL_SWITCH_ENABLED",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_ENDPOINT_MODE",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "ATLAS_RESEARCH_API_KEY",
    "RESEARCH_MODEL",
    "CLICKUP_API_TOKEN",
    "CLICKUP_WORKSPACE_ID",
    "CLICKUP_LIST_ID",
    "CLICKUP_TASK_ID",
    "ALLOW_GIT_COMMIT",
    "ALLOW_GIT_PUSH",
    "GIT_COMMIT_AUTHOR_NAME",
    "GIT_COMMIT_AUTHOR_EMAIL",
    "AI_PROVIDER",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_COMPATIBLE_MODEL",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "KIMI_API_KEY",
    "GROK_API_KEY",
    "OPENROUTER_API_KEY",
    "LOCAL_COMMAND",
)


def test_all_five_routine_prompts_exist() -> None:
    for routine in ROUTINES:
        assert Path("routines/prompts", f"{routine}.md").exists()


def test_routine_prompts_include_required_safety_contract() -> None:
    for routine in ROUTINES:
        text = Path("routines/prompts", f"{routine}.md").read_text(encoding="utf-8")
        lower = text.lower()
        assert "read markdown memory files before acting" in lower
        assert "api keys are read from environment variables" in lower
        assert "do not look for `.env` in the remote routine environment" in lower
        assert "never print api keys" in lower
        assert "never write secrets" in lower
        assert "live execution requires approval" in lower
        assert "memory/" in lower
        assert "reports/" in lower
        assert "allow_git_commit=true" in lower
        assert "allow_git_push=true" in lower
        assert "do not bypass riskmanager" in lower
        assert "bypass risk manager" not in lower


def test_docs_and_prompts_use_same_exact_env_names() -> None:
    docs = Path("docs/environment-variables.md").read_text(encoding="utf-8")
    prompts = "\n".join(
        Path("routines/prompts", f"{routine}.md").read_text(encoding="utf-8")
        for routine in ROUTINES
    )

    for name in ENV_NAMES:
        assert name in docs
        assert name in prompts


def test_prompts_do_not_contain_raw_api_keys() -> None:
    for routine in ROUTINES:
        text = Path("routines/prompts", f"{routine}.md").read_text(encoding="utf-8")
        assert re.search(r"\bsk-[A-Za-z0-9_-]{10,}", text) is None
        assert re.search(r"\bpplx-[A-Za-z0-9_-]{10,}", text) is None
        assert "Bearer " not in text
