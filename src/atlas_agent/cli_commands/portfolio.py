"""CLI handler for `atlas portfolio`."""
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_portfolio(context: CLIContext) -> int | None:
    args = context.args
    config = context.config
    from atlas_agent.cli_io import emit_cli_success
    from atlas_agent.cli import _portfolio_payload

    if args.command == "portfolio" and args.portfolio_command == "show":
        payload = _portfolio_payload(config)
        if getattr(args, "json", False):
            return emit_cli_success("atlas portfolio show", payload)
        print("Portfolio state is local. No live broker query is made by this command.")
        print(f"Workspace: {payload['workspace']}")
        print(f"Trading mode: {payload['trading_mode']}")
        print(f"Live enabled: {payload['live_enabled']}")
        print(f"Broker: {payload['broker']}")
        print(f"Pending orders: {payload['pending_orders']}")
        return 0
    return None

