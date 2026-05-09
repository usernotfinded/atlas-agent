from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel
from datetime import date
from pathlib import Path
from atlas_agent.core.types import *
from atlas_agent.tools.spec import ToolSpec, generate_input_schema

BUILTIN_TOOLS = []

def get_quote(symbols: list[str]) -> dict[str, QuoteData]:
    """Mock implementation of get_quote"""
    return {}

get_quote_spec = ToolSpec(
    name="get_quote",
    description_full="Get the latest price, change, and volume for one or more symbols. Use this when you need a quick price check or to mark positions to market. Do NOT use this to retrieve historical data \u2014 use get_ohlcv instead. Do NOT call this more than once per symbol per reasoning cycle; cache the result in your context.",
    description_compact="Get the latest price, change, and volume for one or more symbols.",
    input_schema=generate_input_schema(get_quote),
    execute=get_quote,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_quote_spec)

def get_ohlcv(symbol: str, timeframe: str, start: date, end: date | None = None) -> list[Bar]:
    """Mock implementation of get_ohlcv"""
    return []

get_ohlcv_spec = ToolSpec(
    name="get_ohlcv",
    description_full="Retrieve historical OHLCV bars for a symbol over a timeframe. Use this to compute indicators, identify levels, or back-test visual patterns. Do NOT use this for real-time tick data \u2014 use get_quote. Do NOT request more data than you need; large downloads slow your reasoning cycle.",
    description_compact="Retrieve historical OHLCV bars for a symbol over a timeframe.",
    input_schema=generate_input_schema(get_ohlcv),
    execute=get_ohlcv,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_ohlcv_spec)

def get_orderbook(symbol: str, depth: int = 10) -> OrderbookSnapshot:
    """Mock implementation of get_orderbook"""
    return OrderbookSnapshot.model_construct()

get_orderbook_spec = ToolSpec(
    name="get_orderbook",
    description_full="Get the Level 2 order book for a symbol. Use this for large-size entries or exits where slippage matters, or to gauge immediate liquidity. Do NOT use this for every order \u2014 most trades do not need microstructure detail.",
    description_compact="Get the Level 2 order book for a symbol.",
    input_schema=generate_input_schema(get_orderbook),
    execute=get_orderbook,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_orderbook_spec)

def get_news(query: str, sources: list[str] | None = None, max_items: int = 10) -> list[NewsItem]:
    """Mock implementation of get_news"""
    return []

get_news_spec = ToolSpec(
    name="get_news",
    description_full="Fetch recent news headlines and summaries for a symbol or topic. Use this to validate or invalidate a thesis based on new information. Do NOT use this to chase headlines for trade ideas \u2014 react to news only if it changes your existing thesis.",
    description_compact="Fetch recent news headlines and summaries for a symbol or topic.",
    input_schema=generate_input_schema(get_news),
    execute=get_news,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_news_spec)

def get_economic_calendar(start: date, end: date, region: str = "US") -> list[EconomicEvent]:
    """Mock implementation of get_economic_calendar"""
    return []

get_economic_calendar_spec = ToolSpec(
    name="get_economic_calendar",
    description_full="Retrieve upcoming macroeconomic events (FOMC, CPI, NFP, earnings). Use this to avoid entering positions just before high-volatility events, or to prepare for post-event reactions. Do NOT ignore this before swing entries.",
    description_compact="Retrieve upcoming macroeconomic events (FOMC, CPI, NFP, earnings).",
    input_schema=generate_input_schema(get_economic_calendar),
    execute=get_economic_calendar,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_economic_calendar_spec)

def get_earnings(symbols: list[str], lookback_days: int = 5, lookahead_days: int = 30) -> list[EarningsItem]:
    """Mock implementation of get_earnings"""
    return []

get_earnings_spec = ToolSpec(
    name="get_earnings",
    description_full="Get upcoming and recent earnings dates, EPS estimates, and surprises for a symbol or universe. Use this for equity-specific timing decisions. Do NOT use this for non-equity assets.",
    description_compact="Get upcoming and recent earnings dates, EPS estimates, and surprises for a symbol or universe.",
    input_schema=generate_input_schema(get_earnings),
    execute=get_earnings,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_earnings_spec)

def compute_indicators(ohlcv: list[Bar], indicators: list[IndicatorSpec]) -> dict[str, IndicatorResult]:
    """Mock implementation of compute_indicators"""
    return {}

compute_indicators_spec = ToolSpec(
    name="compute_indicators",
    description_full="Calculate technical indicators (RSI, MACD, SMA, EMA, ATR, Bollinger, etc.) on provided OHLCV data. Use this when your thesis requires quantitative confirmation. Do NOT use this to cherry-pick indicators that confirm your bias \u2014 state which indicators you are checking and why before calling.",
    description_compact="Calculate technical indicators (RSI, MACD, SMA, EMA, ATR, Bollinger, etc.",
    input_schema=generate_input_schema(compute_indicators),
    execute=compute_indicators,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(compute_indicators_spec)

def run_quick_backtest(universe: list[str], timeframe: str, start: date, end: date, entry_rule: str, exit_rule: str, sizing: str, costs: CostModel) -> BacktestReport:
    """Mock implementation of run_quick_backtest"""
    return BacktestReport.model_construct()

run_quick_backtest_spec = ToolSpec(
    name="run_quick_backtest",
    description_full="Run a fast, deterministic backtest on a rule set you define. Use this when you have a specific tactical idea and want to see how it would have performed historically. Do NOT use this for vague intuitions \u2014 formulate entry_rule and exit_rule as specific expressions. Do NOT use this to prove you are right; use it to discover how you would be wrong. If the backtest sharpe is below 0.5 or max drawdown exceeds your daily loss limit, the idea is likely not viable.",
    description_compact="Run a fast, deterministic backtest on a rule set you define.",
    input_schema=generate_input_schema(run_quick_backtest),
    execute=run_quick_backtest,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(run_quick_backtest_spec)

def monte_carlo_sim(backtest_report_id: str, simulations: int = 1000) -> MonteCarloResult:
    """Mock implementation of monte_carlo_sim"""
    return MonteCarloResult.model_construct()

monte_carlo_sim_spec = ToolSpec(
    name="monte_carlo_sim",
    description_full="Run a Monte Carlo simulation on a strategy's backtest results to estimate confidence intervals for drawdown and return. Use this after a quick backtest to stress-test the robustness. Do NOT use this as a primary decision tool \u2014 it is a sanity check, not a signal.",
    description_compact="Run a Monte Carlo simulation on a strategy's backtest results to estimate confidence intervals for drawdown and return.",
    input_schema=generate_input_schema(monte_carlo_sim),
    execute=monte_carlo_sim,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(monte_carlo_sim_spec)

def correlation_matrix(symbols: list[str], timeframe: str, lookback_days: int = 60) -> CorrelationMatrix:
    """Mock implementation of correlation_matrix"""
    return CorrelationMatrix.model_construct()

correlation_matrix_spec = ToolSpec(
    name="correlation_matrix",
    description_full="Compute the correlation matrix for a universe of symbols over a lookback window. Use this to check for hidden concentration risk before adding a new position. Do NOT use this to justify adding correlated positions.",
    description_compact="Compute the correlation matrix for a universe of symbols over a lookback window.",
    input_schema=generate_input_schema(correlation_matrix),
    execute=correlation_matrix,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(correlation_matrix_spec)

def screen_universe(universe: list[str], filters: list[FilterSpec], max_results: int = 20) -> list[ScreenerResult]:
    """Mock implementation of screen_universe"""
    return []

screen_universe_spec = ToolSpec(
    name="screen_universe",
    description_full="Screen a universe of symbols by quantitative filters (momentum, volatility, volume, fundamental ratios). Use this to generate a watchlist or identify candidates for deeper analysis. Do NOT use this to select trades blindly \u2014 every candidate requires individual thesis validation.",
    description_compact="Screen a universe of symbols by quantitative filters (momentum, volatility, volume, fundamental ratios).",
    input_schema=generate_input_schema(screen_universe),
    execute=screen_universe,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(screen_universe_spec)

def propose_order(symbol: str, side: Literal["buy", "sell"], quantity: float, order_type: Literal["market", "limit"], thesis: TradeThesis, invalidation_price: float, limit_price: float | None = None, stop_loss: float | None = None, take_profit: float | None = None, time_in_force: str = "day") -> OrderProposalResult:
    """Mock implementation of propose_order"""
    return OrderProposalResult.model_construct()

propose_order_spec = ToolSpec(
    name="propose_order",
    description_full="Propose a buy or sell order to the execution pipeline. This is your primary execution tool. Use this ONLY when you have a clear thesis, a named invalidation price, and you have checked your current exposure and risk limits. Do NOT use this to average down on a losing position. Do NOT use this because you are bored or because \"the market might move\". Every call MUST include a non-empty thesis object with all required fields filled thoughtfully. The RiskManager will validate size, exposure, and limits. The trust-mode policy may require human approval before the broker receives the order.",
    description_compact="Propose a buy or sell order to the execution pipeline.",
    input_schema=generate_input_schema(propose_order),
    execute=propose_order,
    risk_gated=True,
    approval_gated=True,
    audit_logged=True,
)
BUILTIN_TOOLS.append(propose_order_spec)

def cancel_order(order_id: str, replacement_order: OrderProposal | None = None) -> OrderResult:
    """Mock implementation of cancel_order"""
    return OrderResult.model_construct()

cancel_order_spec = ToolSpec(
    name="cancel_order",
    description_full="Cancel an open order by its order_id. Use this when the thesis behind a pending order has changed, or when you want to replace an order with a new one. Do NOT use this to circumvent the RiskManager \u2014 if you were rejected, reflect instead of retrying. Do NOT cancel protective orders (stop loss, take profit) without replacing them immediately \u2014 removing protection increases risk.",
    description_compact="Cancel an open order by its order_id.",
    input_schema=generate_input_schema(cancel_order),
    execute=cancel_order,
    risk_gated=True,
    approval_gated=True,
    audit_logged=True,
)
BUILTIN_TOOLS.append(cancel_order_spec)

def modify_order(order_id: str, quantity: float | None = None, limit_price: float | None = None) -> OrderResult:
    """Mock implementation of modify_order"""
    return OrderResult.model_construct()

modify_order_spec = ToolSpec(
    name="modify_order",
    description_full="Modify the quantity or limit price of an open order. Use this to tighten or loosen a limit based on new market conditions. Do NOT use this to increase size beyond what the RiskManager would allow on a fresh order \u2014 the modification is re-validated.",
    description_compact="Modify the quantity or limit price of an open order.",
    input_schema=generate_input_schema(modify_order),
    execute=modify_order,
    risk_gated=True,
    approval_gated=True,
    audit_logged=True,
)
BUILTIN_TOOLS.append(modify_order_spec)

def get_positions() -> list[Position]:
    """Mock implementation of get_positions"""
    return []

get_positions_spec = ToolSpec(
    name="get_positions",
    description_full="Retrieve current open positions from the broker. Use this at session start and after any execution to confirm your internal state matches reality. Do NOT assume your internal memory is correct \u2014 brokers are the source of truth for positions.",
    description_compact="Retrieve current open positions from the broker.",
    input_schema=generate_input_schema(get_positions),
    execute=get_positions,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_positions_spec)

def get_account() -> AccountSnapshot:
    """Mock implementation of get_account"""
    return AccountSnapshot.model_construct()

get_account_spec = ToolSpec(
    name="get_account",
    description_full="Retrieve account snapshot (cash, equity, buying power, margin). Use this to verify you have sufficient capital before proposing an order. Do NOT rely on cached account values from the start of the session.",
    description_compact="Retrieve account snapshot (cash, equity, buying power, margin).",
    input_schema=generate_input_schema(get_account),
    execute=get_account,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_account_spec)

def flatten_position(symbol: str, reason: str, strategy: str = "market", bps: int = 25, urgency: Literal["normal", "protective", "emergency"] = "normal") -> FlattenResult:
    """Mock implementation of flatten_position"""
    return FlattenResult.model_construct()

flatten_position_spec = ToolSpec(
    name="flatten_position",
    description_full="Close an entire position immediately (market or aggressive limit). Use this when a thesis is invalidated, a stop is hit, or you need to reduce exposure urgently. Do NOT use this for routine exits \u2014 use propose_order with the opposite side. Do NOT use this to panic-exit without a reason \u2014 the reason is logged.",
    description_compact="Close an entire position immediately (market or aggressive limit).",
    input_schema=generate_input_schema(flatten_position),
    execute=flatten_position,
    risk_gated=True,
    approval_gated=True,
    audit_logged=True,
)
BUILTIN_TOOLS.append(flatten_position_spec)

def request_user_approval( proposal: OrderProposal | str, context: str, timeout_seconds: int = 3600, options: list[str] = ["approve", "reject", "modify"] ) -> UserResponse:
    """Mock implementation of request_user_approval"""
    return UserResponse.model_construct()

request_user_approval_spec = ToolSpec(
    name="request_user_approval",
    description_full="Present a proposal to the user and pause execution until they respond. Use this in MANUAL mode before every trade, and in SUPERVISED mode when a proposed order exceeds thresholds (size, symbol, timing, leverage). The user can approve, reject, or request modifications. Do NOT use this for informational updates \u2014 use notify_user for fire-and-forget messages. Do NOT use this in AUTONOMOUS mode unless an exceptional situation arises (e.g., an order that you believe violates your own style but the RiskManager approved).",
    description_compact="Present a proposal to the user and pause execution until they respond.",
    input_schema=generate_input_schema(request_user_approval),
    execute=request_user_approval,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(request_user_approval_spec)

def read_journal(symbol: str | None = None, start: date | None = None, end: date | None = None, limit: int = 50) -> list[JournalEntry]:
    """Mock implementation of read_journal"""
    return []

read_journal_spec = ToolSpec(
    name="read_journal",
    description_full="Read entries from the trade journal, optionally filtered by symbol, date range, or tag. Use this at session start to recall recent trades and mistakes. Do NOT use this to justify a current trade by cherry-picking a past winner \u2014 read the full context.",
    description_compact="Read entries from the trade journal, optionally filtered by symbol, date range, or tag.",
    input_schema=generate_input_schema(read_journal),
    execute=read_journal,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_journal_spec)

def append_journal(entry_type: str, content: str, symbol: str | None = None, tags: list[str] | None = None) -> bool:
    """Mock implementation of append_journal"""
    return True

append_journal_spec = ToolSpec(
    name="append_journal",
    description_full="Append a new entry to the trade journal. Use this immediately after every trade execution (win, loss, scratch), and after significant observations. The entry should include: what happened, why (thesis), what you learned, and what you will do differently. Do NOT skip this \u2014 the journal is your only mechanism to not repeat errors.",
    description_compact="Append a new entry to the trade journal.",
    input_schema=generate_input_schema(append_journal),
    execute=append_journal,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(append_journal_spec)

def read_skill(name: str, status: str = "active") -> SkillContent:
    """Mock implementation of read_skill"""
    return SkillContent.model_construct()

read_skill_spec = ToolSpec(
    name="read_skill",
    description_full="Read the full content of a specific skill (active or proposed). Use this when you want to apply a skill's guidance to a current situation. Do NOT use this to invent skills that do not exist.",
    description_compact="Read the full content of a specific skill (active or proposed).",
    input_schema=generate_input_schema(read_skill),
    execute=read_skill,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_skill_spec)

def list_skills(status: str | None = None) -> list[SkillSummary]:
    """Mock implementation of list_skills"""
    return []

list_skills_spec = ToolSpec(
    name="list_skills",
    description_full="List all skills by status (active, proposed, archived). Use this at session start to recall your operational playbook. Do NOT assume a proposed skill is valid \u2014 it is a hypothesis until promoted.",
    description_compact="List all skills by status (active, proposed, archived).",
    input_schema=generate_input_schema(list_skills),
    execute=list_skills,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(list_skills_spec)

def write_skill_proposal(name: str, pattern: str, evidence: str, when_to_use: str, when_to_avoid: str, confidence: str = "low") -> Path:
    """Mock implementation of write_skill_proposal"""
    return Path('mock')

write_skill_proposal_spec = ToolSpec(
    name="write_skill_proposal",
    description_full="Write a new proposed skill to the skills/proposed/ folder. Use this ONLY after observing a pattern that has held across at least 5-10 trades or sessions and that you believe improves your edge. A skill is a generalization of recurring lessons. Before calling this, verify that lessons_learned.md contains multiple entries (5+) pointing in the same direction \u2014 cite them in the evidence field. Do NOT propose a skill based on a single trade or a hunch. Do NOT promote a skill immediately after proposing it \u2014 let it sit in proposed for at least a few sessions to gather more data. If you are unsure, write to lessons_learned.md instead \u2014 it has lower commitment.",
    description_compact="Write a new proposed skill to the skills/proposed/ folder.",
    input_schema=generate_input_schema(write_skill_proposal),
    execute=write_skill_proposal,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(write_skill_proposal_spec)

def promote_skill(name: str, reason: str) -> bool:
    """Mock implementation of promote_skill"""
    return True

promote_skill_spec = ToolSpec(
    name="promote_skill",
    description_full="Promote a proposed skill to active status. Use this when you have gathered additional evidence that confirms the proposed skill's validity. Do NOT promote a skill immediately after proposing it \u2014 let it sit in proposed for at least a few sessions to gather more data.",
    description_compact="Promote a proposed skill to active status.",
    input_schema=generate_input_schema(promote_skill),
    execute=promote_skill,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(promote_skill_spec)

def archive_skill(name: str, reason: str) -> bool:
    """Mock implementation of archive_skill"""
    return True

archive_skill_spec = ToolSpec(
    name="archive_skill",
    description_full="Move an active or proposed skill to archived status. Use this when a skill has stopped working, when market regime changes invalidate it, or when you realize it was overfit. Be honest \u2014 archiving a bad skill is as important as promoting a good one.",
    description_compact="Move an active or proposed skill to archived status.",
    input_schema=generate_input_schema(archive_skill),
    execute=archive_skill,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(archive_skill_spec)

def read_user_profile() -> str:
    """Mock implementation of read_user_profile"""
    return 'mock'

read_user_profile_spec = ToolSpec(
    name="read_user_profile",
    description_full="Read the user_profile.md file. Use this at session start to remember who you are trading for, their constraints, and their preferences. Do NOT modify this file.",
    description_compact="Read the user_profile.",
    input_schema=generate_input_schema(read_user_profile),
    execute=read_user_profile,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_user_profile_spec)

def update_user_profile(section: str, content: str) -> bool:
    """Mock implementation of update_user_profile"""
    return True

update_user_profile_spec = ToolSpec(
    name="update_user_profile",
    description_full="Append an observation or derived preference to the user_profile.md under the \"Agent Observations\" section. Use this when you notice a consistent preference or constraint that the user has not explicitly written. Do NOT overwrite sections written by the user. Do NOT write assumptions as facts.",
    description_compact="Append an observation or derived preference to the user_profile.",
    input_schema=generate_input_schema(update_user_profile),
    execute=update_user_profile,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(update_user_profile_spec)

def read_trading_style() -> str:
    """Mock implementation of read_trading_style"""
    return 'mock'

read_trading_style_spec = ToolSpec(
    name="read_trading_style",
    description_full="Read the trading_style.md file. Use this at session start to remember your binding constraints.",
    description_compact="Read the trading_style.",
    input_schema=generate_input_schema(read_trading_style),
    execute=read_trading_style,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_trading_style_spec)

def read_open_positions() -> str:
    """Mock implementation of read_open_positions"""
    return 'mock'

read_open_positions_spec = ToolSpec(
    name="read_open_positions",
    description_full="Read the cached open_positions.md file. Use this to review the narrative state of your positions.",
    description_compact="Read the cached open_positions.",
    input_schema=generate_input_schema(read_open_positions),
    execute=read_open_positions,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_open_positions_spec)

def update_open_positions(content: str) -> bool:
    """Mock implementation of update_open_positions"""
    return True

update_open_positions_spec = ToolSpec(
    name="update_open_positions",
    description_full="Update the open_positions.md file with the latest snapshot.",
    description_compact="Update the open_positions.",
    input_schema=generate_input_schema(update_open_positions),
    execute=update_open_positions,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(update_open_positions_spec)

def update_portfolio_summary(content: str) -> bool:
    """Mock implementation of update_portfolio_summary"""
    return True

update_portfolio_summary_spec = ToolSpec(
    name="update_portfolio_summary",
    description_full="Update the portfolio.md summary file.",
    description_compact="Update the portfolio.",
    input_schema=generate_input_schema(update_portfolio_summary),
    execute=update_portfolio_summary,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(update_portfolio_summary_spec)

def read_mistakes(limit: int = 10) -> list[str]:
    """Mock implementation of read_mistakes"""
    return []

read_mistakes_spec = ToolSpec(
    name="read_mistakes",
    description_full="Read the mistakes.md file.",
    description_compact="Read the mistakes.",
    input_schema=generate_input_schema(read_mistakes),
    execute=read_mistakes,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_mistakes_spec)

def append_mistake(content: str) -> bool:
    """Mock implementation of append_mistake"""
    return True

append_mistake_spec = ToolSpec(
    name="append_mistake",
    description_full="Append a new mistake to mistakes.md.",
    description_compact="Append a new mistake to mistakes.",
    input_schema=generate_input_schema(append_mistake),
    execute=append_mistake,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(append_mistake_spec)

def append_daily_note(content: str) -> bool:
    """Mock implementation of append_daily_note"""
    return True

append_daily_note_spec = ToolSpec(
    name="append_daily_note",
    description_full="Append an observation to daily_notes.md during the session.",
    description_compact="Append an observation to daily_notes.",
    input_schema=generate_input_schema(append_daily_note),
    execute=append_daily_note,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(append_daily_note_spec)

def search_memory(query: str, mode: str = "hybrid", top_n: int = 10) -> list[SearchResult]:
    """Mock implementation of search_memory"""
    return []

search_memory_spec = ToolSpec(
    name="search_memory",
    description_full="Search across all memory files using hybrid search (BM25 + vector + rerank). Use this when you need to recall a specific past observation, lesson, or trade detail but do not know which file it is in. Do NOT use this as a substitute for reading structured files like user_profile or open_positions \u2014 use those directly when you know what you need.",
    description_compact="Search across all memory files using hybrid search (BM25 + vector + rerank).",
    input_schema=generate_input_schema(search_memory),
    execute=search_memory,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(search_memory_spec)

def read_lessons_learned(limit: int = 30) -> list[LessonEntry]:
    """Mock implementation of read_lessons_learned"""
    return []

read_lessons_learned_spec = ToolSpec(
    name="read_lessons_learned",
    description_full="Read entries from lessons_learned.md. Use this at session start to recall what you have already learned and should not need to re-discover. Do NOT assume a lesson from six months ago still applies \u2014 market regimes change.",
    description_compact="Read entries from lessons_learned.",
    input_schema=generate_input_schema(read_lessons_learned),
    execute=read_lessons_learned,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_lessons_learned_spec)

def append_lesson(content: str, category: str = "general", related_symbols: list[str] | None = None) -> bool:
    """Mock implementation of append_lesson"""
    return True

append_lesson_spec = ToolSpec(
    name="append_lesson",
    description_full="Append a lesson to lessons_learned.md. Use this at the end of a session when you noticed a mistake, a pattern, or a refinement to your process. A good lesson is specific and actionable: \"When X happens, I should do Y instead of Z because...\". Do NOT write vague platitudes like \"be more disciplined\" \u2014 that is not a lesson, it is a wish. Use this for observations that are specific to a situation but not yet generalized into a repeatable pattern. Lessons are individual data points. If you find yourself writing many lessons that say similar things, that is the signal to formalize a skill via write_skill_proposal.",
    description_compact="Append a lesson to lessons_learned.",
    input_schema=generate_input_schema(append_lesson),
    execute=append_lesson,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(append_lesson_spec)

def read_recent_trades(limit: int = 20) -> TradeSummary:
    """Mock implementation of read_recent_trades"""
    return TradeSummary.model_construct()

read_recent_trades_spec = ToolSpec(
    name="read_recent_trades",
    description_full="Read the last N trades from the trade journal, formatted as a summary table with PnL and tags. Use this to review recent performance before making a new decision. Do NOT use this to cherry-pick a winning streak to justify a new trade.",
    description_compact="Read the last N trades from the trade journal, formatted as a summary table with PnL and tags.",
    input_schema=generate_input_schema(read_recent_trades),
    execute=read_recent_trades,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_recent_trades_spec)

def summarize_session(notes: str, trades: list[str], lessons: list[str], next_focus: str) -> bool:
    """Mock implementation of summarize_session"""
    return True

summarize_session_spec = ToolSpec(
    name="summarize_session",
    description_full="Write a structured session summary to daily_notes.md. Use this at the end of every session (or when the user asks for a recap). Include: trades executed, lessons learned, skills proposed or promoted, market observations, and plan for next session. Do NOT use this mid-session \u2014 it is a closing ritual.",
    description_compact="Write a structured session summary to daily_notes.",
    input_schema=generate_input_schema(summarize_session),
    execute=summarize_session,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(summarize_session_spec)

def web_search(query: str, max_results: int = 5) -> list[SearchResultItem]:
    """Mock implementation of web_search"""
    return []

web_search_spec = ToolSpec(
    name="web_search",
    description_full="Search the public web for information. Use this when you need context on a company, macro event, or sector narrative that is not in your memory. Do NOT use this for real-time prices \u2014 use get_quote. Do NOT use this to confirm your existing bias; use it to challenge your thesis.",
    description_compact="Search the public web for information.",
    input_schema=generate_input_schema(web_search),
    execute=web_search,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(web_search_spec)

def read_url(url: str, max_chars: int = 8000) -> str:
    """Mock implementation of read_url"""
    return 'mock'

read_url_spec = ToolSpec(
    name="read_url",
    description_full="Fetch and read the text content of a specific URL. Use this when a web_search result points to a document you need to read in full. Do NOT use this to browse indiscriminately \u2014 have a specific question you need answered.",
    description_compact="Fetch and read the text content of a specific URL.",
    input_schema=generate_input_schema(read_url),
    execute=read_url,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(read_url_spec)

def market_research(query: str, depth: str = "standard") -> ResearchReport:
    """Mock implementation of market_research"""
    return ResearchReport.model_construct()

market_research_spec = ToolSpec(
    name="market_research",
    description_full="Run a deep research query via the configured web research provider. Use this for complex, multi-faceted questions where web_search would be too shallow. Do NOT use this for simple facts \u2014 it is slow and expensive. Save the result to your memory if it is reusable.",
    description_compact="Run a deep research query via the configured web research provider.",
    input_schema=generate_input_schema(market_research),
    execute=market_research,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(market_research_spec)

# Legacy alias for backward compatibility
perplexity_research_spec = ToolSpec(
    name="perplexity_research",
    description_full="Legacy alias for market_research.",
    description_compact="Legacy alias for market_research.",
    input_schema=generate_input_schema(market_research),
    execute=market_research,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(perplexity_research_spec)

def get_current_time() -> TimeInfo:
    """Mock implementation of get_current_time"""
    return TimeInfo.model_construct()

get_current_time_spec = ToolSpec(
    name="get_current_time",
    description_full="Get the current UTC and local time. Use this to timestamp reasoning, check session boundaries, and verify market hours. Do NOT assume you know the time \u2014 you do not.",
    description_compact="Get the current UTC and local time.",
    input_schema=generate_input_schema(get_current_time),
    execute=get_current_time,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_current_time_spec)

def get_market_status() -> dict[str, MarketStatus]:
    """Mock implementation of get_market_status"""
    return {}

get_market_status_spec = ToolSpec(
    name="get_market_status",
    description_full="Get the current market status for configured markets (US equities, crypto, forex, etc.). Use this to know what is tradable right now. Do NOT use this to decide whether to run \u2014 the agent loop runs regardless; this informs what you can trade.",
    description_compact="Get the current market status for configured markets (US equities, crypto, forex, etc.",
    input_schema=generate_input_schema(get_market_status),
    execute=get_market_status,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_market_status_spec)

def get_my_limits() -> LimitsSnapshot:
    """Mock implementation of get_my_limits"""
    return LimitsSnapshot.model_construct()

get_my_limits_spec = ToolSpec(
    name="get_my_limits",
    description_full="Read the current risk limits, trust mode, and portfolio guardrails. Use this before proposing any order to verify you are within bounds. Do NOT rely on memory of limits from a previous session \u2014 limits can change.",
    description_compact="Read the current risk limits, trust mode, and portfolio guardrails.",
    input_schema=generate_input_schema(get_my_limits),
    execute=get_my_limits,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_my_limits_spec)

def get_my_trust_mode() -> TrustModeInfo:
    """Mock implementation of get_my_trust_mode"""
    return TrustModeInfo.model_construct()

get_my_trust_mode_spec = ToolSpec(
    name="get_my_trust_mode",
    description_full="Read the current trust mode (MANUAL, SUPERVISED, AUTONOMOUS) and its active policy rules. Use this to know whether you need approval before executing. Do NOT guess the trust mode \u2014 it is a configuration fact.",
    description_compact="Read the current trust mode (MANUAL, SUPERVISED, AUTONOMOUS) and its active policy rules.",
    input_schema=generate_input_schema(get_my_trust_mode),
    execute=get_my_trust_mode,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(get_my_trust_mode_spec)

def run_shell_command(cmd: list[str], cwd: str = "workspace", timeout: int = 30) -> ShellResult:
    """Mock implementation of run_shell_command"""
    return ShellResult.model_construct()

run_shell_command_spec = ToolSpec(
    name="run_shell_command",
    description_full="Execute a shell command inside the workspace directory. Use this ONLY when you need to run a local script, process a CSV, or perform a system operation that no other tool covers. Do NOT use this to bypass other tools. Do NOT use this to access files outside the workspace. Do NOT use this to read secrets or credentials. Do NOT use this to modify files in the forbidden paths list \u2014 these are protected by code-level sandbox, not by your intent. Every command is logged.",
    description_compact="Execute a shell command inside the workspace directory.",
    input_schema=generate_input_schema(run_shell_command),
    execute=run_shell_command,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(run_shell_command_spec)

def git_commit_memory(message: str) -> str:
    """Mock implementation of git_commit_memory"""
    return 'mock'

git_commit_memory_spec = ToolSpec(
    name="git_commit_memory",
    description_full="Commit the current state of memory/ and reports/ to git. Use this at the end of a session if you want to preserve your memory in version control. Do NOT use this after every small write \u2014 it is noisy and slow.",
    description_compact="Commit the current state of memory/ and reports/ to git.",
    input_schema=generate_input_schema(git_commit_memory),
    execute=git_commit_memory,
    risk_gated=False,
    approval_gated=False,
    audit_logged=True,
)
BUILTIN_TOOLS.append(git_commit_memory_spec)

def notify_user(message: str, priority: str = "normal", channel: str = "default") -> bool:
    """Mock implementation of notify_user"""
    return True

notify_user_spec = ToolSpec(
    name="notify_user",
    description_full="Send a notification to the user through the configured messaging gateway (Telegram, webhook, email, etc.). Use this in SUPERVISED or AUTONOMOUS mode to report trade executions, rejections, or important alerts. In MANUAL mode, use this to present a trade idea and wait for user response. Do NOT use this for internal reasoning \u2014 only for user-facing communication.",
    description_compact="Send a notification to the user through the configured messaging gateway (Telegram, webhook, email, etc.",
    input_schema=generate_input_schema(notify_user),
    execute=notify_user,
    risk_gated=False,
    approval_gated=False,
    audit_logged=False,
)
BUILTIN_TOOLS.append(notify_user_spec)
