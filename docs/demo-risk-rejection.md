# Demo: Risk Rejection

> **Not financial advice.** Atlas Agent is a software tool, not a financial advisor. Trading involves significant risk of loss.

Atlas Agent uses deterministic risk gates that operate independently of the LLM. This demo shows how an unsafe order is blocked before it reaches any broker.

## How risk gating works

1. The LLM (or a tool call) proposes an order.
2. `RiskManager.validate_order()` evaluates it against hard-coded limits.
3. If the order violates a limit, it is rejected with a clear reason.
4. The broker's `place_order()` is **never called**.

## Reference price requirement

Market orders without a `limit_price` require a valid `market_price`. If neither is available, the order is rejected with:

```
Cannot evaluate notional for market order without reference price
reference_price_required
```

Limit orders use their `limit_price` for notional calculation.

## Reproducing a rejection

You can trigger a risk rejection programmatically or by violating a configured limit:

### Example: exceeding max position size

Set a very low position limit in `.atlas/config.toml`:

```toml
[risk]
max_position_notional = 50.0
```

Then validate:

```bash
atlas validate
```

If a future agent cycle proposes an order with notional greater than $50, the `RiskManager` will reject it.

### Example: market order without reference price (programmatic)

```python
from atlas_agent.execution.order import Order
from atlas_agent.portfolio.state import PortfolioState
from atlas_agent.risk.manager import RiskManager
from atlas_agent.config import AtlasConfig

config = AtlasConfig()
manager = RiskManager.from_config(config)

# Market order with no limit_price and a zero market_price
order = Order(symbol="AAPL", side="buy", quantity=10, order_type="market", limit_price=None)
portfolio = PortfolioState(cash=10000.0)

decision = manager.validate_order(order, portfolio, mode="paper", market_price=0.0)

assert not decision.allowed
assert "reference_price_required" in decision.reasons
```

Expected result:

```
decision.allowed = False
decision.reasons = ("Cannot evaluate notional for market order without reference price", "reference_price_required")
```

## What to verify

- Rejected orders do not create entries in `pending_orders/`.
- An audit event records the rejected/blocked decision.
- No live broker order is sent.

## Important

Do not bypass the risk gates. If you need different limits, change them in `.atlas/config.toml` and re-run `atlas validate`.
