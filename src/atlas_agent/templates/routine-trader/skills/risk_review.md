# Risk Review Skill

Use before any order proposal or execution.

Inputs: proposed order, mode, portfolio state, risk config, kill switch state.

Outputs: risk concerns and whether deterministic `RiskManager` should allow or reject.

Safety rules: defer to deterministic `RiskManager`; do not override rejection; kill switch blocks everything; live mode requires stop loss and approval.

Failure modes: missing price, blocked symbol, max loss exceeded, max position size exceeded, duplicate order.

Example: reject a buy when projected notional exceeds `MAX_POSITION_SIZE`.
