# Trading Decision Skill

Use when converting research, strategy signals, and memory into buy, sell, hold, reduce, close, or increase.

Inputs: research summary, strategy signal, memory files, portfolio state, risk limits.

Outputs: structured decision JSON with action, symbol, confidence, time horizon, reasoning summary, risk notes, and proposed order.

Safety rules: low confidence must hold; AI output is advisory; never call broker APIs; never bypass RiskManager.

Failure modes: missing data, invalid decision schema, low confidence, conflicting signals.

Example: produce a hold decision when research is uncertain and confidence is below threshold.

