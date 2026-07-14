# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/audit.py
# PURPOSE: CLI handler for `atlas audit` — verifies the hash-chained audit trail and
#          reports whether it has been tampered with.
# DEPS:    atlas_agent.audit (verification), cli_io (envelopes)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

from atlas_agent.audit import verify_audit_log, verify_run_manifest
from atlas_agent.cli_context import CLIContext


def handle_audit(context: CLIContext) -> int:
    args = context.args
    config = context.config

    if args.audit_command == "verify":
        if args.all:
            manifest_dir = config.audit_dir / "manifests"
            if not manifest_dir.exists():
                print("No manifests found.")
                return 0
            manifests = list(manifest_dir.glob("*.json"))
            if not manifests:
                print("No manifests found.")
                return 0

            print(f"Verifying {len(manifests)} manifests...")
            all_valid = True
            for manifest_path in sorted(manifests):
                result = verify_run_manifest(manifest_path)
                status_icon = "✅" if result.valid else "❌"
                print(f"{status_icon} {manifest_path.name}: {result.manifest_status}")
                if not result.valid:
                    all_valid = False
                    for error in result.errors:
                        print(f"  - {error}")
            return 0 if all_valid else 2

        if args.manifest:
            result = verify_run_manifest(args.manifest)
            if result.valid:
                print(
                    f"Audit manifest verification successful. Checked {result.events_checked} events."
                )
                print(f"Status: {result.manifest_status.upper()}")
                return 0
            print(
                f"Audit manifest verification FAILED. Checked {result.events_checked} events."
            )
            print(f"Status: {result.manifest_status.upper()}")
            for error in result.errors:
                print(f"- {error}")
            return 2

        path = args.path or (config.audit_dir / "events.jsonl")
        result = verify_audit_log(path)
        if result.valid:
            print(
                f"Audit log verification successful. Checked {result.events_checked} events."
            )
            return 0
        print(
            f"Audit log verification FAILED. Checked {result.events_checked} events."
        )
        for error in result.errors:
            print(f"- {error}")
        return 2

    return 0
