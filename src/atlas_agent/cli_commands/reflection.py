# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/reflection.py
# PURPOSE: CLI handler for `atlas reflection` — generate, review and approve
#          reflection artifacts.
# DEPS:    reflection.generator, reflection.approval, reflection.storage
# ==============================================================================

"""CLI handler for `atlas reflection`."""

# --- IMPORTS ---
from __future__ import annotations

import sys

from pathlib import Path

from atlas_agent.cli_context import CLIContext


def handle_reflection(context: CLIContext) -> int | None:
    args = context.args
    import json

    if args.command == "reflection":
        from atlas_agent.reflection.generator import generate_reflection
        from atlas_agent.reflection.storage import save_artifact, load_artifact, list_artifacts
        from atlas_agent.reflection.approval import approve, reject, archive, submit_for_review
        from atlas_agent.reflection.renderers import render_markdown as _render_reflection_markdown

        if args.reflection_command == "create":
            input_path = getattr(args, "input", None)
            kind = getattr(args, "kind", None)
            output = getattr(args, "output", "stdout")
            use_json = getattr(args, "json", False)
            artifact = generate_reflection(
                input_path,
                kind=kind,
                workspace=".",
                dry_run=True,
            )
            save_artifact(artifact, workspace=".")
            if use_json:
                content = artifact.model_dump_json(indent=2)
            else:
                content = _render_reflection_markdown(artifact)
            if output == "stdout":
                print(content)
            else:
                out_path = Path(output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(content, encoding="utf-8")
                print(f"Reflection written to: {out_path}")
            return 0

        if args.reflection_command == "list":
            status_filter = getattr(args, "status", None)
            use_json = getattr(args, "json", False)
            from atlas_agent.reflection.models import ReflectionStatus
            status = ReflectionStatus(status_filter) if status_filter else None
            artifacts = list_artifacts(workspace=".", status=status)
            if use_json:
                print(json.dumps(artifacts, indent=2, sort_keys=True, default=str))
            else:
                if not artifacts:
                    print("No reflection artifacts found.")
                    return 0
                print(f"{'ID':<36} {'Status':<16} {'Kind':<12} {'Generated'}")
                print("-" * 80)
                for a in artifacts:
                    print(f"{a['reflection_id']:<36} {a['status']:<16} {a['kind']:<12} {a['generated_at']}")
            return 0

        if args.reflection_command == "show":
            reflection_id = getattr(args, "reflection_id", None)
            use_json = getattr(args, "json", False)
            artifact = load_artifact(reflection_id, workspace=".")
            if use_json:
                print(artifact.model_dump_json(indent=2))
            else:
                print(_render_reflection_markdown(artifact))
            return 0

        if args.reflection_command == "submit":
            reflection_id = getattr(args, "reflection_id", None)
            artifact = load_artifact(reflection_id, workspace=".")
            submit_for_review(artifact, workspace=".")
            print(f"Reflection {reflection_id} submitted for review.")
            return 0

        if args.reflection_command == "approve":
            reflection_id = getattr(args, "reflection_id", None)
            reason = getattr(args, "reason", "")
            artifact = load_artifact(reflection_id, workspace=".")
            approve(artifact, reason=reason or None, workspace=".")
            print(f"Reflection {reflection_id} approved.")
            return 0

        if args.reflection_command == "reject":
            reflection_id = getattr(args, "reflection_id", None)
            reason = getattr(args, "reason", "")
            if not reason:
                print("Error: --reason is required for rejection.", file=sys.stderr)
                return 1
            artifact = load_artifact(reflection_id, workspace=".")
            reject(artifact, reason=reason, workspace=".")
            print(f"Reflection {reflection_id} rejected.")
            return 0

        if args.reflection_command == "archive":
            reflection_id = getattr(args, "reflection_id", None)
            reason = getattr(args, "reason", "")
            artifact = load_artifact(reflection_id, workspace=".")
            archive(artifact, reason=reason or None, workspace=".")
            print(f"Reflection {reflection_id} archived.")
            return 0

        print("Error: Use 'atlas reflection --help' for usage.")
        return 1
    return None

