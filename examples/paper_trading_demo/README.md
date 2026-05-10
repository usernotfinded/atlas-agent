# Paper Trading Demo

Paper trading is the default and safest way to run Atlas Agent. It uses the high-fidelity `PaperBrokerAdapter` to simulate execution without any financial risk.

## Quickstart
Run a single autonomous cycle in paper mode:
```bash
atlas run --mode paper --once
```

Run continuously (default 60s interval):
```bash
atlas run --mode paper --continuous
```

## Features
- **Deterministic Risk**: All paper orders are validated by the `RiskManager`.
- **Full Audit**: Every simulated action is recorded in the tamper-evident audit hash-chain.
- **Realistic Fills**: Uses historical market data to simulate realistic fill prices.

