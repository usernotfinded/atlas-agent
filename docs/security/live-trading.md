# Live Trading Security

Live trading in Atlas is strictly opt-in and disabled by default. 

## Invariants

1. **Paper Default**: Atlas runs in paper trading mode unless explicitly configured otherwise.
2. **Approval Gates**: All live orders require explicit human approval (`atlas approve-order`). 
3. **Remote Control Plane**: The Telegram webhook server is optional, disabled by default, and requires the operator to provide their own authenticated ASGI/FastAPI runner (e.g., `uvicorn`). When wired, it does not bypass the local RiskManager or the human approval requirement. Tokens and secrets used for remote authentication are strictly redacted and never logged.
4. **Kill Switch**: Live executions immediately check the kill switch state and fail securely if it is activated or tampered with.
