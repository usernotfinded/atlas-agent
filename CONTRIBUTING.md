# Contributing to Atlas Agent

Thank you for your interest in contributing to Atlas Agent. Atlas Agent is a local-first, self-improving AI trading agent designed for precision, safety, and transparency.

## Contribution Priorities

We prioritize contributions that improve the reliability and safety of the agent. Please align your work with these priorities:

1.  **Bug Fixes**: Addressing crashes, incorrect behavior, data loss, or broken setup flows.
2.  **Safety and Risk Hardening**: Improving live-trading gates, the kill switch, approval gates, and the correctness of the Risk Manager.
3.  **Secret and Config Safety**: Ensuring API keys and `.env.atlas` files are never leaked, committed, or accidentally overwritten during updates.
4.  **Provider Compatibility**: Improving support for OpenAI-compatible APIs, Anthropic, OpenRouter, and local models.
5.  **Tool Registry Correctness**: Refining tool schemas, validation logic, descriptions, and audit/risk/approval flags.
6.  **Cross-Platform Compatibility**: Ensuring smooth operation on macOS, Linux, and WSL2.
7.  **Testing and CI Robustness**: Adding unit and integration tests to cover critical execution paths.
8.  **Documentation**: Improving clarity for onboarding and development.
9.  **New Features**: Adding capabilities that fit the roadmap without compromising safety or simplicity.

## What Should Be a Tool, Provider, Guardrail, or Agent Feature?

To maintain a clean architecture, follow these guidelines when deciding where to add new functionality:

Do not hardcode a preferred research/search vendor in user-facing documentation, setup flows, or tests. Research/search/browser integrations should be provider adapters. Secrets must go to .env.atlas; non-secret settings must go to .atlas/config.json. Standardize on `ATLAS_RESEARCH_API_KEY` for research-related secrets.

### Make it a Tool when:
- The LLM needs to call it as an explicit action. (Tool: action exposed to the LLM)
- It interacts with market data, broker actions, portfolio state, memory, research, trade journals, or user notifications.
- It requires a stable JSON schema for model consumption.
- It must be validated by the `ToolRegistry` and may require safety flags (audit, risk, or approval).
- **Backward Compatibility:** When renaming a tool, keep the old name as a legacy alias in `BUILTIN_TOOLS` to prevent breaking existing reasoning loops.

*Examples: `get_quote`, `get_ohlcv`, `propose_order`, `cancel_order`, `append_journal`, `request_user_approval`, `notify_user`.*

### Make it a Provider Adapter when:
- It normalizes one vendor/backend into Atlas internal research/search/browser shapes.
- It normalizes model-specific output into the internal `LLMResponse` or `ToolCall` models.
- It handles native tool calling or implements JSON fallback parsing for a specific model family.
- It is responsible for communication with the AI vendor, not trading logic.

### Make it a Guardrail/Risk/Safety component when:
- It blocks unsafe or invalid trading behavior independently of the LLM. (Guardrail: deterministic safety/risk blocker)
- It enforces risk limits (e.g., position size, daily loss) via the **RiskManager**.
- It manages emergency states via the **KillSwitch**.
- It creates or executes emergency interventions via the **SafetyActionPlanner** or **SafetyActionExecutor**.
- It protects sensitive files, paths, or execution states.

### Make it Agent Loop logic when:
- It manages how context is composed for the LLM in the **AgentLoop**.
- It coordinates session state and routes tool results back into the reasoning flow.
- It handles the high-level coordination of an autonomous tool-driven loop.

### Make it an Audit component when:
- It records immutable, tamper-evident logs via the **Audit Hash-Chain**.
- It manages run-level **Audit Manifests** and root hashes.

### Make it a Broker component when:
- It synchronizes account state, positions, and orders via the **BrokerSyncService**.

### Make it a Dashboard component when:
- It provides read-only local visibility into the system state via the **Dashboard**.

### Make it Setup Wizard logic when:
- It collects config and secrets, but never stores API keys in config.json.

### Do NOT add a new tool when:
- A simple schema correction to an existing tool is sufficient.
- The capability is a trading strategy disguised as infrastructure.
- It bypasses risk controls, approval gates, or audit logging.

## Development Setup

Atlas Agent requires Python 3.11+.

```bash
# Clone the repository
git clone https://github.com/usernotfinded/atlas-agent.git
cd atlas-agent

# Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies and the package in editable mode
python -m pip install --upgrade pip
python -m pip install -e .

# Verify the installation
atlas
```

The first time you run `atlas`, it may open the interactive setup wizard if configuration is missing. You can also run `atlas validate` to check your environment.

## Configuration for Development

- **`.atlas/config.json`**: Stores non-secret workspace configuration.
- **`.env.atlas`**: Stores sensitive API keys and broker credentials. This file must **never** be committed.
- **`atlas configure`**: The official command to (re)configure your environment.
- **`atlas update`**: Preserves your secrets and local configuration while updating the codebase.

| File | Purpose | Commit? |
| :--- | :--- | :--- |
| `.atlas/config.json` | Local Atlas configuration | No (unless used as a test fixture) |
| `.env.atlas` | API keys and secrets | **Never** |
| `.env` / `.env.local` | Local environment secrets | **Never** |
| `pyproject.toml` | Package metadata and dependencies | Yes |
| `README.md` / `CONTRIBUTING.md` | Documentation | Yes |

**Contributor Rule:** Never print, log, snapshot, or commit real API keys or secrets.

## Running Tests

We use `pytest` for testing. Ensure you are in your virtual environment.

```bash
# Run all tests
python3.11 -m pytest

# Check for dependency issues
python3.11 -m pip check

# Run targeted tests
python3.11 -m pytest tests/tools/
python3.11 -m pytest tests/test_provider_adapters.py
python3.11 -m pytest tests/update/
python3.11 -m pytest tests/safety/
```

- Run the full test suite before opening a Pull Request.
- Always use Python 3.11, as CI and project validation target this version.
- Do not rely on the `python` alias in test scripts; prefer `python3.11` or `sys.executable`.

## Project Structure

```text
src/atlas_agent/
├── agent/            # Agent loop, planning, and runner logic
├── ai/               # High-level AI interfaces and response models
├── brokers/          # Broker adapters (Paper, Alpaca, Binance, CCXT)
├── execution/        # Order routing, audit logging, and approval management
├── market_data/      # Data providers (CSV, etc.)
├── providers/        # Provider adapters (Anthropic, OpenAI, etc.)
├── risk/             # Deterministic risk manager and policy gates
├── safety/           # Kill switch, TOTP, and dead-man heartbeats
├── setup/            # Interactive setup wizard and onboarding logic
├── tools/            # Tool Registry and builtin tool implementations
├── update/           # Safe update manager
└── cli.py            # Primary CLI entry point
```

## Architecture Overview

```text
User / Scheduler / Event
        ↓
CLI / Setup / Session
        ↓
Agent Context + Provider Adapter
        ↓
LLMResponse / ToolCall normalization
        ↓
Tool Registry
        ↓
Market Data / Research / Memory / Broker / Update / User Approval
        ↓
Risk Gates / Guardrails / Audit / Safety Controls
```

- **Provider adapters** convert raw model output into normalized internal objects.
- **ToolRegistry** validates arguments against JSON schemas before execution.
- **Risk Gates** independently verify every order proposal regardless of LLM "confidence."

## Adding or Modifying a Tool

Every tool must be safe, documented, and predictable.

1.  **Stable Signature**: Use explicit Python types. Avoid `**kwargs` unless absolutely necessary.
2.  **Clear Descriptions**: Tell the model exactly when to use (and when *not* to use) the tool.
3.  **Strict Validation**: Schemas should reject invalid types or extra arguments (`additionalProperties: false`).
4.  **Safety Flags**: Trading and execution tools must be `risk_gated=True`, `approval_gated=True`, and `audit_logged=True`.
5.  **Mockable**: Provide a safe implementation that returns a typed value for testing.

**Checklist:**
- [ ] Signature matches the intended JSON schema.
- [ ] Required fields are correctly marked in the schema.
- [ ] Risk/approval/audit flags are set correctly for the tool's impact.
- [ ] Tests cover valid input, missing required fields, and type mismatches.

## Provider Adapter Guidelines

- Normalization must handle both native tool calling (e.g., OpenAI/Anthropic) and JSON fallback parsing.
- Adapters must reject unknown tools or invalid argument shapes.
- **Do not** include trading or risk logic inside a provider adapter.
- Adapters should never execute tools directly; they only return `ToolCall` objects.

## Setup Wizard Guidelines

- The wizard must be interactive-friendly and preserve the Atlas banner.
- Use full-screen/clean UI flows that do not pollute terminal scrollback.
- It must fail safely in non-interactive environments (CI, pipes).
- It must never leak or log secrets during the collection process.

## Update System Guidelines

- `atlas update` is the only official way to update a deployed workspace.
- The updater must **never** overwrite local `.env.atlas` or secret files.
- Conservative safety patterns (denylists) must be strictly enforced.
- Any change to the update logic must include safety tests to prevent secret overwrites.

## Trading Safety Guidelines

Trading is dangerous. Atlas Agent prioritizes the protection of the user's capital.

- **Paper Mode First**: Never weaken paper-mode defaults.
- **Live Trading is Opt-in**: Live execution must require explicit configuration and multiple safety gates.
- **No Bypass**: Never allow LLM output to bypass the `RiskManager`.
- **Review Critical Changes**: Any change to `execution/`, `risk/`, or `safety/` is considered safety-critical and requires deep review.
- **No Auto-Approve**: We do not support "auto-approve" for live trading unless core and heavily guarded.
- **Protections**: Tools must never average down on losing positions or remove stop-loss protections without immediate replacement.

## Security Considerations

- **No Secret Logging**: Never log API keys, tokens, or broker secrets.
- **Path Validation**: Tools like `run_shell_command` must be restricted to the workspace and prevented from accessing forbidden paths or secrets.
- **Subprocess Safety**: Always use list-form calls (`subprocess.run(["ls", "-l"])`) to avoid shell injection.
- **Leak Prevention**: Do not expose credentials in exception messages or CLI output.

## Cross-Platform Compatibility

- Use `pathlib.Path` for all file operations.
- Avoid assuming a specific shell (e.g., `bash`) exists; use `sys.executable` for Python calls.
- Use `UTF-8` encoding for all file reads and writes.
- Be careful with file permissions and path separators on Windows/WSL2.

## Code Style

- **Explicit is better than implicit**: Prefer typed dataclasses and Pydantic models.
- **Deterministic**: Avoid non-deterministic behavior in core logic.
- **Small Functions**: Keep functions focused and testable.
- **Specific Exceptions**: Avoid broad `except Exception` blocks unless re-raising or logging at the top level.

## Pull Request Process

1.  **Focus**: One logical change per PR. Do not mix refactors, features, and documentation.
2.  **Tests**: Include tests for every change.
3.  **Safety**: Clearly state if your PR touches risk or safety-critical modules.
4.  **No Artifacts**: Ensure no local `.atlas/`, `.env*`, or `__pycache__` files are included.

**Branch Naming:**
- `fix/description`
- `feat/description`
- `docs/description`
- `test/description`

**Commit Messages (Conventional Commits):**
- `fix(cli): prevent bare atlas from starting execution`
- `feat(setup): add secure credential onboarding`
- `test(tools): validate schema rejection paths`

## Issue Reports

When reporting a bug, please include:
- Operating System and Python version.
- Atlas Agent version (`atlas --version` or `pip show atlas-agent`).
- The exact command run and the full traceback.
- Whether you were in paper or live mode.
- The AI provider used (do **not** include your API key).

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
