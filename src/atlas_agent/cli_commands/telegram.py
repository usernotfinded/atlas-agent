"""CLI handler for `atlas telegram`."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_telegram(context: CLIContext) -> int | None:
    args = context.args
    config = context.config
    from atlas_agent.cli_safety import _effective_config_with_runtime_kill_switch
    from atlas_agent.cli_safety import _kill_switch_controller
    from atlas_agent.execution.audit import AuditLogger
    from atlas_agent.portfolio.state import PortfolioState
    from atlas_agent.safety import write_deadman_heartbeat
    from atlas_agent.cli import (
        _broker_for_mode,
        _heartbeat_path_for_config,
    )

    if args.command == "telegram":
        from atlas_agent.telegram_control import (
            TELEGRAM_COMMANDS,
            get_telegram_diagnostics,
            verify_resume_totp_from_env,
        )

        if args.telegram_command == "test":
            print(get_telegram_diagnostics().format())
            return 0
        if args.telegram_command == "kill":
            controller = _kill_switch_controller(config)
            runtime_config = _effective_config_with_runtime_kill_switch(config)
            broker = _broker_for_mode(
                runtime_config.trading_mode,
                runtime_config,
                PortfolioState(cash=runtime_config.starting_cash),
                AuditLogger(runtime_config.audit_dir),
            )
            transition = controller.enable(
                mode=args.mode,
                reason=args.reason,
                actor="telegram",
                broker=broker,
            )
            print(
                f"Telegram /kill applied: changed={transition.changed} "
                f"mode={transition.state.mode}"
            )
            return 0
        if args.telegram_command == "resume":
            controller = _kill_switch_controller(config)
            state = controller.status()
            if not verify_resume_totp_from_env(args.totp or ""):
                print("Telegram /resume refused: invalid or missing TOTP")
                return 2
            transition = controller.disable(reason=args.reason, actor="telegram")
            print(
                f"Telegram /resume applied: changed={transition.changed} "
                f"prev_mode={state.mode}"
            )
            return 0
        if args.telegram_command == "heartbeat":
            path = _heartbeat_path_for_config(config)
            write_deadman_heartbeat(path, source=args.source, actor=args.actor)
            print(f"Telegram heartbeat recorded: {path}")
            return 0
        if args.telegram_command == "run":
            print("Telegram control plane adapter is optional and stdlib-only in this package.")
            print(
                "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_IDS, "
                "then wire polling/webhook in your deployment wrapper."
            )
            print("Commands: " + ", ".join(TELEGRAM_COMMANDS))
            return 0
    return None

