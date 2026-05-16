# atlas-agent-architecture

## When to use this skill

- Adding or removing CLI commands
- Restructuring the CLI entrypoint (`cli.py`) into smaller modules
- Creating new service modules or changing import boundaries
- Moving code out of `cli.py` into `cli_commands/`, `services/`, or other packages
- Changing the command registry pattern
- Addressing circular import issues
- Creating compatibility wrappers during refactoring

## Files and areas this applies to

- `src/atlas_agent/cli.py`
- `src/atlas_agent/cli_commands/`
- `src/atlas_agent/cli_context.py`
- Any new command handler module
- `src/atlas_agent/__init__.py` (import surface)
- Service boundary layers (broker, execution, audit, risk)

## Non-negotiable rules

1. **`atlas_agent.cli:main` must remain the public CLI entrypoint.** Never rename or remove it. Internal refactoring is allowed, but the public contract stays.
2. **Decomposition must not break existing commands.** If a command handler moves to a new module, the old CLI path must continue to work. Prefer gradual migration with compatibility wrappers.
3. **Do not create god files.** If a new module exceeds ~400 lines of business logic, decompose it. Exception: `cli.py` may remain large during gradual migration, but new commands should target `cli_commands/` or dedicated modules.
4. **Avoid circular imports.** If introducing a new shared module causes circular imports, use deferred imports inside functions or introduce a thin protocol/interface module.
5. **Keep provider/broker/execution layers independent.** The research module must not import broker adapters. The audit module must not import execution order routers. Use event logging or thin interfaces for cross-module communication.
6. **CLI command registry changes require parser updates.** If `build_parser()` changes, verify that `atlas --help` still works and all subcommands remain reachable.

## Required checks

- [ ] `atlas --help` exits 0 and lists expected commands
- [ ] `atlas <command> --help` exits 0 for every modified command
- [ ] `python3.11 -c "from atlas_agent.cli import main; main()"` exits 0 (no import errors)
- [ ] No new circular import warnings when running `pytest`
- [ ] `python3.11 -m pytest tests/cli -q` passes (if CLI tests exist)

## Required tests or verification commands

```bash
python3.11 -c "from atlas_agent.cli import main; import sys; sys.exit(main(['--help']))"
python3.11 -m pytest tests/ -q -k "cli"
python3.11 -m pytest tests/ -q
```

## Output format expected

When restructuring, produce:
1. A brief rationale for the decomposition
2. A list of moved functions/classes and their new locations
3. A compatibility plan (wrapper, import alias, or explicit deprecation)
4. Confirmation that `atlas --help` and affected command `--help` still work

## Common failure modes to avoid

- **Breaking argparse wiring.** Moving a subparser definition without updating the handler dispatch in `main()` causes silent command disappearance.
- **Import side effects.** Top-level imports in new modules that trigger config loading or broker initialization cause `pytest` failures and slow startup.
- **Forgetting handler dispatch.** Adding a parser but not wiring `if args.command == ... and args.subcommand == ...` in `main()`.
- **Over-decomposition.** Creating a module for a single 20-line function adds navigation overhead without benefit.
- **Removing deprecated imports too early.** Give at least one release cycle before removing compatibility wrappers.
