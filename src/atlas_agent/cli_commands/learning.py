"""CLI handler for `atlas learning`."""
from __future__ import annotations

import sys

from atlas_agent.cli_context import CLIContext


def handle_learning(context: CLIContext) -> int | None:
    args = context.args
    import json
    config = context.config

    if args.command == "learning":
        from atlas_agent.learning.generator import (
            generate_suggestion_from_input,
        )
        from atlas_agent.learning.storage import (
            save_suggestion,
            load_suggestion,
            list_suggestions,
        )
        from atlas_agent.learning.approval import (
            submit_for_review,
            accept,
            reject,
            archive,
        )
        from atlas_agent.learning.renderers import render_markdown as _render_learning_markdown, render_json_string as _render_learning_json

        workspace = str(config.workspace_root)

        if args.learning_command == "suggest":
            suggestion = generate_suggestion_from_input(
                args.input,
                kind=getattr(args, "kind", None),
                workspace=workspace,
                dry_run=getattr(args, "dry_run", True),
            )
            save_suggestion(suggestion, workspace=workspace)
            if getattr(args, "json", False):
                print(_render_learning_json(suggestion))
            else:
                print(f"Learning suggestion created: {suggestion.suggestion_id}")
            return 0

        if args.learning_command == "suggest-from-reflection":
            print("Use 'atlas learning suggest --input <reflection-path> --kind reflection' instead.")
            return 0

        if args.learning_command == "suggest-from-skill":
            print("Use 'atlas learning suggest --input <skill-path> --kind skill' instead.")
            return 0

        if args.learning_command == "list-suggestions":
            from atlas_agent.learning.models import SuggestionStatus
            status_filter = None
            status_arg = getattr(args, "status", None)
            if status_arg:
                status_filter = SuggestionStatus(status_arg)
            items = list_suggestions(workspace=workspace, status=status_filter)
            if getattr(args, "json", False):
                print(json.dumps(items, indent=2, sort_keys=True, default=str))
            else:
                if not items:
                    print("No learning suggestions found.")
                    return 0
                print(f"{'ID':<36} {'Status':<16} {'Kind':<12} {'Created'}")
                for item in items:
                    print(f"{item['suggestion_id']:<36} {item['status']:<16} {item['kind']:<12} {item['created_at']}")
            return 0

        if args.learning_command == "show-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            suggestion = load_suggestion(suggestion_id, workspace=workspace)
            if getattr(args, "json", False):
                print(_render_learning_json(suggestion))
            else:
                print(_render_learning_markdown(suggestion))
            return 0

        if args.learning_command == "submit-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                submit_for_review(suggestion, workspace=workspace)
                print(f"Suggestion {suggestion_id} submitted for review.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        if args.learning_command == "accept-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            reason = getattr(args, "reason", "")
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                accept(suggestion, reason=reason or None, workspace=workspace)
                print(f"Suggestion {suggestion_id} accepted.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        if args.learning_command == "reject-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            reason = getattr(args, "reason", "")
            if not reason:
                print("Error: --reason is required for rejection.", file=sys.stderr)
                return 1
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                reject(suggestion, reason=reason, workspace=workspace)
                print(f"Suggestion {suggestion_id} rejected.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        if args.learning_command == "archive-suggestion":
            suggestion_id = getattr(args, "suggestion_id", None)
            reason = getattr(args, "reason", "")
            try:
                suggestion = load_suggestion(suggestion_id, workspace=workspace)
                archive(suggestion, reason=reason or None, workspace=workspace)
                print(f"Suggestion {suggestion_id} archived.")
            except ValueError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            return 0

        print("Error: Use 'atlas learning --help' for usage.")
        return 1
    return None

