# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tools/mock_impl.py
# PURPOSE: The deterministic mock behind every builtin tool. Nothing here reaches a
#          market, a broker, a shell or the network — the tool CONTRACTS are real,
#          the implementations are simulations.
# DEPS:    core.types
#
# NOTE:    Deterministic on purpose. A mock that returned random data would make the
#          agent's decisions unreproducible, and an unreproducible decision cannot be
#          audited or replayed.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

# ruff: noqa: F403, F405

from datetime import date
from pathlib import Path
from typing import Literal

from atlas_agent.core.types import *  # noqa: F403,F405

MOCK_IMPLEMENTATION_NOTICE = (
    "Builtin tool implementations are deterministic mocks for tests and local dry runs; "
    "they are not live market, broker, notification, shell, or research integrations."
)

__all__ = [
    "get_quote",
    "get_ohlcv",
    "get_orderbook",
    "get_news",
    "get_economic_calendar",
    "get_earnings",
    "compute_indicators",
    "run_quick_backtest",
    "monte_carlo_sim",
    "correlation_matrix",
    "screen_universe",
    "propose_order",
    "cancel_order",
    "modify_order",
    "get_positions",
    "get_account",
    "flatten_position",
    "request_user_approval",
    "read_journal",
    "append_journal",
    "read_skill",
    "list_skills",
    "write_skill_proposal",
    "promote_skill",
    "archive_skill",
    "read_user_profile",
    "update_user_profile",
    "read_trading_style",
    "read_open_positions",
    "update_open_positions",
    "update_portfolio_summary",
    "read_mistakes",
    "append_mistake",
    "append_daily_note",
    "search_memory",
    "read_lessons_learned",
    "append_lesson",
    "read_recent_trades",
    "summarize_session",
    "web_search",
    "read_url",
    "market_research",
    "get_current_time",
    "get_market_status",
    "get_my_limits",
    "get_my_trust_mode",
    "run_shell_command",
    "git_commit_memory",
    "notify_user",
    "MOCK_IMPLEMENTATION_NOTICE",
]

def get_quote(symbols: list[str]) -> dict[str, QuoteData]:
    """Mock implementation of get_quote"""
    return {}

def get_ohlcv(symbol: str, timeframe: str, start: date, end: date | None = None) -> list[Bar]:
    """Mock implementation of get_ohlcv"""
    return []

def get_orderbook(symbol: str, depth: int = 10) -> OrderbookSnapshot:
    """Mock implementation of get_orderbook"""
    return OrderbookSnapshot.model_construct()

def get_news(query: str, sources: list[str] | None = None, max_items: int = 10) -> list[NewsItem]:
    """Mock implementation of get_news"""
    return []

def get_economic_calendar(start: date, end: date, region: str = "US") -> list[EconomicEvent]:
    """Mock implementation of get_economic_calendar"""
    return []

def get_earnings(symbols: list[str], lookback_days: int = 5, lookahead_days: int = 30) -> list[EarningsItem]:
    """Mock implementation of get_earnings"""
    return []

def compute_indicators(ohlcv: list[Bar], indicators: list[IndicatorSpec]) -> dict[str, IndicatorResult]:
    """Mock implementation of compute_indicators"""
    return {}

def run_quick_backtest(universe: list[str], timeframe: str, start: date, end: date, entry_rule: str, exit_rule: str, sizing: str, costs: CostModel) -> BacktestReport:
    """Mock implementation of run_quick_backtest"""
    return BacktestReport.model_construct()

def monte_carlo_sim(backtest_report_id: str, simulations: int = 1000) -> MonteCarloResult:
    """Mock implementation of monte_carlo_sim"""
    return MonteCarloResult.model_construct()

def correlation_matrix(symbols: list[str], timeframe: str, lookback_days: int = 60) -> CorrelationMatrix:
    """Mock implementation of correlation_matrix"""
    return CorrelationMatrix.model_construct()

def screen_universe(universe: list[str], filters: list[FilterSpec], max_results: int = 20) -> list[ScreenerResult]:
    """Mock implementation of screen_universe"""
    return []

def propose_order(symbol: str, side: Literal["buy", "sell"], quantity: float, order_type: Literal["market", "limit"], thesis: TradeThesis, invalidation_price: float, limit_price: float | None = None, stop_loss: float | None = None, take_profit: float | None = None, time_in_force: str = "day") -> OrderProposalResult:
    """Mock implementation of propose_order"""
    return OrderProposalResult.model_construct()

def cancel_order(order_id: str, replacement_order: OrderProposal | None = None) -> OrderResult:
    """Mock implementation of cancel_order"""
    return OrderResult.model_construct()

def modify_order(order_id: str, quantity: float | None = None, limit_price: float | None = None) -> OrderResult:
    """Mock implementation of modify_order"""
    return OrderResult.model_construct()

def get_positions() -> list[Position]:
    """Mock implementation of get_positions"""
    return []

def get_account() -> AccountSnapshot:
    """Mock implementation of get_account"""
    return AccountSnapshot.model_construct()

def flatten_position(symbol: str, reason: str, strategy: str = "market", bps: int = 25, urgency: Literal["normal", "protective", "emergency"] = "normal") -> FlattenResult:
    """Mock implementation of flatten_position"""
    return FlattenResult.model_construct()

def request_user_approval( proposal: OrderProposal | str, context: str, timeout_seconds: int = 3600, options: list[str] = ["approve", "reject", "modify"] ) -> UserResponse:
    """Mock implementation of request_user_approval"""
    return UserResponse.model_construct()

def read_journal(symbol: str | None = None, start: date | None = None, end: date | None = None, limit: int = 50) -> list[JournalEntry]:
    """Mock implementation of read_journal"""
    return []

def append_journal(entry_type: str, content: str, symbol: str | None = None, tags: list[str] | None = None) -> bool:
    """Mock implementation of append_journal"""
    return True

def read_skill(name: str, status: str = "active") -> SkillContent:
    """Mock implementation of read_skill"""
    return SkillContent.model_construct()

def list_skills(status: str | None = None) -> list[SkillSummary]:
    """Mock implementation of list_skills"""
    return []

def write_skill_proposal(name: str, pattern: str, evidence: str, when_to_use: str, when_to_avoid: str, confidence: str = "low") -> Path:
    """Mock implementation of write_skill_proposal"""
    return Path('mock')

def promote_skill(name: str, reason: str) -> bool:
    """Mock implementation of promote_skill"""
    return True

def archive_skill(name: str, reason: str) -> bool:
    """Mock implementation of archive_skill"""
    return True

def read_user_profile() -> str:
    """Mock implementation of read_user_profile"""
    return 'mock'

def update_user_profile(section: str, content: str) -> bool:
    """Mock implementation of update_user_profile"""
    return True

def read_trading_style() -> str:
    """Mock implementation of read_trading_style"""
    return 'mock'

def read_open_positions() -> str:
    """Mock implementation of read_open_positions"""
    return 'mock'

def update_open_positions(content: str) -> bool:
    """Mock implementation of update_open_positions"""
    return True

def update_portfolio_summary(content: str) -> bool:
    """Mock implementation of update_portfolio_summary"""
    return True

def read_mistakes(limit: int = 10) -> list[str]:
    """Mock implementation of read_mistakes"""
    return []

def append_mistake(content: str) -> bool:
    """Mock implementation of append_mistake"""
    return True

def append_daily_note(content: str) -> bool:
    """Mock implementation of append_daily_note"""
    return True

def search_memory(query: str, mode: str = "hybrid", top_n: int = 10) -> list[SearchResult]:
    """Mock implementation of search_memory"""
    return []

def read_lessons_learned(limit: int = 30) -> list[LessonEntry]:
    """Mock implementation of read_lessons_learned"""
    return []

def append_lesson(content: str, category: str = "general", related_symbols: list[str] | None = None) -> bool:
    """Mock implementation of append_lesson"""
    return True

def read_recent_trades(limit: int = 20) -> TradeSummary:
    """Mock implementation of read_recent_trades"""
    return TradeSummary.model_construct()

def summarize_session(notes: str, trades: list[str], lessons: list[str], next_focus: str) -> bool:
    """Mock implementation of summarize_session"""
    return True

def web_search(query: str, max_results: int = 5) -> list[SearchResultItem]:
    """Mock implementation of web_search"""
    return []

def read_url(url: str, max_chars: int = 8000) -> str:
    """Mock implementation of read_url"""
    return 'mock'

def market_research(query: str, depth: str = "standard") -> ResearchReport:
    """Mock implementation of market_research"""
    return ResearchReport.model_construct()

def get_current_time() -> TimeInfo:
    """Mock implementation of get_current_time"""
    return TimeInfo.model_construct()

def get_market_status() -> dict[str, MarketStatus]:
    """Mock implementation of get_market_status"""
    return {}

def get_my_limits() -> LimitsSnapshot:
    """Mock implementation of get_my_limits"""
    return LimitsSnapshot.model_construct()

def get_my_trust_mode() -> TrustModeInfo:
    """Mock implementation of get_my_trust_mode"""
    return TrustModeInfo.model_construct()

def run_shell_command(cmd: list[str], cwd: str = "workspace", timeout: int = 30) -> ShellResult:
    """Mock implementation of run_shell_command"""
    return ShellResult.model_construct()

def git_commit_memory(message: str) -> str:
    """Mock implementation of git_commit_memory"""
    return 'mock'

def notify_user(message: str, priority: str = "normal", channel: str = "default") -> bool:
    """Mock implementation of notify_user"""
    return True
