# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/discipline.py
# PURPOSE: CLI handler for `atlas discipline` — sets up and validates the trading
#          discipline profile. Without a valid one, agentic runs fail closed, so
#          this command is a prerequisite for the agent doing anything at all.
# DEPS:    ai.discipline (validation, including the prompt-injection blocklist)
# ==============================================================================

"""CLI handler for `atlas discipline`."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_discipline(context: CLIContext) -> int | None:
    args = context.args

    if args.command == "discipline":
        from atlas_agent.ai.discipline import (
            _DISCIPLINE_SECTIONS,
            _REQUIRED_SAFETY_SENTENCE,
            default_discipline_text,
            discipline_path,
            discipline_status,
            load_user_discipline,
            sanitize_discipline_text,
            validate_discipline_text,
            write_user_discipline,
        )

        if args.discipline_command == "show":
            user_text = load_user_discipline(".")
            if user_text:
                print(user_text)
            else:
                print("# No user discipline profile configured.")
                print("# Atlas will not run agentic workflows until one is set.")
                print()
                print("# Default template (non-operational, for reference only):")
                print(default_discipline_text())
            return 0
        if args.discipline_command == "validate":
            user_text = load_user_discipline(".")
            if not user_text:
                print("No user discipline file found.")
                return 0
            ok, errors = validate_discipline_text(user_text)
            if ok:
                print("Discipline profile is valid.")
                return 0
            print("Discipline profile has errors:")
            for err in errors:
                print(f"  - {err}")
            return 2
        if args.discipline_command == "set":
            raw_text = " ".join(args.text)

            content = sanitize_discipline_text(raw_text)
            # If the user provided a full profile with sections, use it as-is
            has_sections = sum(1 for s in _DISCIPLINE_SECTIONS if f"## {s}" in content)
            if has_sections < len(_DISCIPLINE_SECTIONS):
                # Wrap freeform text into a minimal valid profile
                content = (
                    "# Atlas User Discipline Profile\n\n"
                    "## Decision temperament\n\n"
                    f"{content}\n\n"
                    "## Reasoning style\n\n"
                    "Step-by-step and transparent. Explain assumptions and label uncertainties.\n\n"
                    "## Communication style\n\n"
                    "Concise, structured, and respectful.\n\n"
                    "## Risk posture\n\n"
                    "Conservative. Every proposed order must acknowledge risk limits.\n\n"
                    "## Uncertainty handling\n\n"
                    "Explicitly state confidence levels and missing information.\n\n"
                    "## No-trade bias\n\n"
                    "Default to no action unless the case is compelling.\n\n"
                    "## Forbidden overrides\n\n"
                    f"{_REQUIRED_SAFETY_SENTENCE}\n"
                )
            # Ensure required safety sentence is present
            if _REQUIRED_SAFETY_SENTENCE not in content:
                content = content + "\n\n## Forbidden overrides\n\n" + _REQUIRED_SAFETY_SENTENCE + "\n"
            ok, errors = validate_discipline_text(content)
            if not ok:
                print("Discipline profile has errors:")
                for err in errors:
                    print(f"  - {err}")
                return 2
            write_user_discipline(".", content)
            print(f"Discipline profile saved to {discipline_path('.')}")
            return 0
        if args.discipline_command == "generate":
            from atlas_agent.ai.discipline import build_discipline_generation_prompt

            # Print the generation prompt so the user can pipe it to their LLM
            print(build_discipline_generation_prompt("I want a cautious, evidence-based trading analyst."))
            return 0
        if args.discipline_command == "reset":
            path = discipline_path(".")
            if path.exists():
                path.unlink()
                print("User discipline profile removed.")
            else:
                print("No user discipline profile to reset.")
            return 0
        if args.discipline_command == "setup":
            path = discipline_path(".")
            if path.exists():
                print(f"Discipline profile already exists at {path}")
                print("Use `atlas discipline reset` first if you want to replace it.")
                return 1
            if args.manual:
                template = default_discipline_text()
                if not args.yes:
                    print("The following template will be written to .atlas/discipline.md:")
                    print("---")
                    print(template)
                    print("---")
                    try:
                        confirm = input("Confirm? [yes/no]: ").strip().lower()
                    except EOFError:
                        confirm = "no"
                    if confirm != "yes":
                        print("Setup cancelled.")
                        return 130
                write_user_discipline(".", template)
                print(f"Discipline profile created at {path}")
                return 0
            else:
                print("Run `atlas discipline setup --manual` to create from the default template.")
                print("Or use `atlas discipline set <text>` to provide your own.")
                print("Or use `atlas discipline generate` to produce a prompt for your LLM.")
                return 0
        if args.discipline_command == "doctor":
            status = discipline_status(".")
            print(f"Path: {status['path']}")
            print(f"Configured: {status['configured']}")
            print(f"Valid: {status['valid']}")
            if status["errors"]:
                print("Errors:")
                for err in status["errors"]:
                    print(f"  - {err}")
            return 0
    return None

