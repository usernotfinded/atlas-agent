# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/broker.py
# PURPOSE: CLI handler for `atlas broker` — shows which broker is resolved and what
#          it is permitted to do (sync? submit?), without ever placing an order.
# DEPS:    brokers.resolver, brokers.status
# ==============================================================================

"""CLI handler for `atlas broker`."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_broker(context: CLIContext) -> int | None:
    args = context.args
    import json
    config = context.config
    resolution = context.resolution
    from atlas_agent.cli import (
        _cmd_broker_opt_in,
        _cmd_broker_opt_out,
    )

    if args.command == "broker" and args.brokers_command == "list":
        print("paper, alpaca, binance, ccxt, ibkr_stub")
        return 0
    if args.command == "broker" and args.brokers_command == "status":
        from atlas_agent.brokers.resolver import BrokerResolver
        from atlas_agent.brokers.status import list_broker_support_inventory

        resolver = BrokerResolver(config)
        inventory = [
            {
                "support": entry.to_dict(),
                "runtime": resolver.resolve_status(
                    "paper" if entry.broker_id == "paper" else "live"
                ).to_dict()
                if entry.broker_id != "paper" or config is not None
                else resolver.resolve_status("paper").to_dict(),
            }
            for entry in list_broker_support_inventory()
        ]
        if getattr(args, "json", False):
            print(json.dumps({"inventory": inventory}, indent=2))
            return 0

        print("Broker Support Inventory")
        print("-" * 60)
        for item in inventory:
            support = item["support"]
            runtime = item["runtime"]
            print(f"{support['display_name']} ({support['broker_id']})")
            print(f"  Status             : {support['status']}")
            print(f"  Paper supported    : {support['paper_supported']}")
            print(f"  Read-only supported: {support['read_only_supported']}")
            print(f"  Live submit support: {support['live_submit_supported']}")
            print(f"  Requires opt-in    : {support['requires_explicit_opt_in']}")
            print(f"  Default enabled    : {support['default_enabled']}")
            print(f"  Runtime code       : {runtime['code']}")
            print(f"  Notes              : {support['notes']}")
            print()
        return 0
    if args.command == "broker" and args.brokers_command == "sync":
        from atlas_agent.brokers.resolver import BrokerResolver
        from atlas_agent.brokers.sync import BrokerSyncService
        from atlas_agent.brokers.models import BrokerSyncResult

        mode = getattr(args, "mode", "paper")
        resolver = BrokerResolver(config)
        resolution = resolver.resolve_sync_provider(mode)

        if resolution.sync_provider is None:
            result = BrokerSyncResult(
                status="failed",
                errors=[resolution.status.message],
                diagnostics={"broker_status": resolution.status.to_dict()},
            )
        else:
            sync_service = BrokerSyncService(broker=resolution.sync_provider)
            result = sync_service.sync()

        if getattr(args, "json", False):
            print(result.model_dump_json(indent=2))
            return 0

        print(f"Broker Sync Result: {result.status.upper()}")
        print(f"  Synced At: {result.synced_at}")
        if result.account:
            print(f"  Account ID: {result.account.account_id}")
            print(f"  Live: {result.account.is_live}")
            print(f"  Cash: ${result.account.cash:,.2f}")
            print(f"  Equity: ${result.account.equity:,.2f}")
        print(f"  Positions: {len(result.positions)}")
        print(f"  Open Orders: {len(result.open_orders)}")
        if result.errors:
            print("  Errors:")
            for err in result.errors:
                print(f"    - {err}")
        return 0 if result.status == "success" else 2
    if args.command == "broker" and args.brokers_command == "opt-in":
        return _cmd_broker_opt_in(args, config)
    if args.command == "broker" and args.brokers_command == "opt-out":
        return _cmd_broker_opt_out(args, config)
    return None

