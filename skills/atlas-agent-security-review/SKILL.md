# atlas-agent-security-review

## When to use this skill

- Any code change that handles secrets, API keys, tokens, or passwords
- Changes to live-mode guards, kill-switch logic, or TOTP verification
- Changes that execute shell commands or subprocess calls
- Changes to exception handling, error messages, or diagnostic output
- Changes to broker error propagation or redaction
- Changes to `.gitignore`, workspace initialization, or runtime file placement
- Any new network call or external data source integration

## Files and areas this applies to

- `src/atlas_agent/safety/` (kill switch, TOTP, secrets)
- `src/atlas_agent/redaction.py` and `src/atlas_agent/audit/redaction.py`
- `src/atlas_agent/brokers/` (error handling, credential access)
- `src/atlas_agent/cli.py` (diagnostic output, `--help`, error envelopes)
- `.gitignore`
- `src/atlas_agent/execution/` (order errors, broker responses)
- Any new module that handles external data

## Non-negotiable rules

1. **Secrets must never appear in stdout, stderr, logs, events, audit records, or exception text.** This includes API keys, passwords, bearer tokens, and secret-shaped values.
2. **Redaction must happen at the source.** Do not rely on downstream consumers to redact. If a value might be sensitive, redact it before serialization.
3. **Live mode must remain opt-in.** Never change defaults to enable live trading, live sync, or live submit. Every live path must require explicit configuration and user confirmation.
4. **Shell execution must be safe.** Avoid `os.system()`, `subprocess.call(shell=True)`, and string-concatenated shell commands. Use `subprocess.run()` with explicit argument lists.
5. **Runtime files must not be committed.** `memory.sqlite`, audit logs, event logs, kill-switch state, pending orders, and generated caches must be in `.gitignore`.
6. **Exception messages must be static.** Do not interpolate raw user input, file paths, broker responses, or secret-shaped values into exception text.
7. **Provider errors must be redacted.** If a broker or AI provider returns an error containing headers, bodies, or credentials, strip them before logging or displaying.

## Required checks

- [ ] `grep -r "API_KEY\|SECRET\|TOKEN\|PASSWORD" src/atlas_agent/` shows only redacted access or safe constant definitions
- [ ] `python3.11 scripts/check_forbidden_claims.py` passes
- [ ] `python3.11 scripts/check_no_protected_staged.py` passes
- [ ] New `.gitignore` entries added for any new runtime file paths
- [ ] No `shell=True` in new subprocess calls
- [ ] No raw exception text in JSON error envelopes

## Required tests or verification commands

```bash
python3.11 scripts/check_forbidden_claims.py
python3.11 scripts/check_no_protected_staged.py
git diff -- .gitignore
python3.11 -m pytest tests/ -q -k "redact or secret or safety"
```

## Output format expected

When reviewing a security-sensitive change, produce:
1. A list of secret-touching code paths identified
2. Confirmation of redaction at each path
3. Live-mode guard status (opt-in remains enforced)
4. Any new `.gitignore` entries needed
5. A go/no-go recommendation

## Common failure modes to avoid

- **Logging raw broker responses.** Broker errors often contain request IDs or headers that look like secrets. Redact them.
- **Printing config dicts.** Config objects may contain credentials. Never `print(config)` or include config in JSON payloads without redaction.
- **Dynamic exception messages with user input.** Path traversal attempts or invalid IDs must be masked as `<invalid>` rather than echoed raw.
- **Forgetting `.gitignore` for new runtime files.** If code creates a new state file, it must be ignored.
- **Assuming upstream redaction.** A downstream logger might not exist. Redact at the source.
