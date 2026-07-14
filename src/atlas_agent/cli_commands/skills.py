# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    cli_commands/skills.py
# PURPOSE: CLI handler for `atlas skills` — propose, diff, approve and PROMOTE
#          skills. Promotion is the consequential verb: it moves a proposal into
#          the set of rules the agent actually follows.
# DEPS:    skills.manager, skills.approval, skills.library
# ==============================================================================

"""CLI handler for `atlas skills`."""

# --- IMPORTS ---
from __future__ import annotations


from atlas_agent.cli_context import CLIContext


def handle_skills(context: CLIContext) -> int | None:
    args = context.args
    import json
    config = context.config
    from atlas_agent.cli_io import display_path
    from atlas_agent.cli_io import emit_cli_success
    from atlas_agent.events import EventLogger
    from atlas_agent.events import generate_run_id

    if args.command == "skills":
        from atlas_agent.skills import (
            archive_skill,
            approve_skill,
            diff_skill,
            improve_proposed_skills,
            list_skills,
            show_skill,
        )
        from atlas_agent.learning.skill_miner import mine_skills_from_journal, save_proposed_skill
        skills_dir = config.memory_dir.parent / "skills"

        if args.skills_command == "list":
            skills = list_skills(skills_dir)
            if getattr(args, "json", False):
                return emit_cli_success("atlas skills list", skills)
            for cat, files in skills.items():
                print(f"{cat.upper()}:")
                for f in files:
                    print(f"  - {f}")
            return 0
        elif args.skills_command == "propose" or args.skills_command == "create-from-journal":
            event_logger = EventLogger(config.events_dir)
            run_id = generate_run_id()
            proposed = mine_skills_from_journal(config.memory_dir)
            for s in proposed:
                path = save_proposed_skill(skills_dir, s)
                event_logger.write(
                    "skill_proposed",
                    run_id=run_id,
                    command=f"atlas skills {args.skills_command}",
                    mode="paper",
                    payload={"skill": path.name},
                )
                print(f"Proposed skill created: {path.name}")
            if not proposed:
                print("No new skills identified from journal.")
            return 0
        elif args.skills_command == "approve":
            try:
                path = approve_skill(skills_dir, args.skill_name)
                print(f"Skill approved and activated: {path}")
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            return 0
        elif args.skills_command == "archive":
            try:
                path = archive_skill(skills_dir, args.skill_name)
                print(f"Skill archived: {path}")
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            return 0
        elif args.skills_command == "improve":
            improved = improve_proposed_skills(skills_dir)
            if not improved:
                print("No proposed skills found to improve.")
                return 0
            event_logger = EventLogger(config.events_dir)
            run_id = generate_run_id()
            print("Improved proposed skill drafts; active skills unchanged:")
            for path in improved:
                event_logger.write(
                    "skill_improved",
                    run_id=run_id,
                    command="atlas skills improve",
                    mode="paper",
                    payload={"skill": path.name},
                )
                print(f"- {display_path(path)}")
            return 0
        elif args.skills_command == "show":
            try:
                skill = show_skill(skills_dir, args.skill_name)
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            print(f"Skill: {args.skill_name}")
            print(f"Path: {skill['path']}")
            print(f"Status: {skill['status']}")
            metadata = skill["metadata"]
            if isinstance(metadata, dict):
                print("Metadata:")
                for key, value in metadata.items():
                    print(f"- {key}: {value}")
            return 0
        elif args.skills_command == "diff":
            try:
                lines = diff_skill(skills_dir, args.skill_name)
            except FileNotFoundError as exc:
                print(f"Error: {exc}")
                return 2
            if not lines:
                print("No differences between active and proposed skill versions.")
                return 0
            print("\n".join(lines))
            return 0

        # Skill candidate handlers
        if args.skills_command == "create-candidate":
            from atlas_agent.skills.generator import generate_candidate_from_input
            from atlas_agent.skills.storage import save_candidate
            from atlas_agent.skills.renderers import render_markdown as _render_skill_markdown

            input_path = getattr(args, "input", None)
            kind = getattr(args, "kind", None)
            use_json = getattr(args, "json", False)
            candidate = generate_candidate_from_input(
                input_path,
                kind=kind,
                workspace=str(config.workspace_root),
                dry_run=True,
            )
            save_candidate(candidate, workspace=str(config.workspace_root))
            if use_json:
                print(candidate.model_dump_json(indent=2))
            else:
                print(f"Skill candidate {candidate.candidate_id} created.")
            return 0

        if args.skills_command == "list-candidates":
            from atlas_agent.skills.models import SkillCandidateStatus
            from atlas_agent.skills.storage import list_candidates

            status_filter = getattr(args, "status", None)
            use_json = getattr(args, "json", False)
            status = SkillCandidateStatus(status_filter) if status_filter else None
            items = list_candidates(workspace=str(config.workspace_root), status=status)
            if use_json:
                print(json.dumps(items, indent=2, sort_keys=True, default=str))
            else:
                if not items:
                    print("No skill candidates found.")
                    return 0
                print(f"{'ID':<36} {'Status':<16} {'Kind':<12} {'Title'}")
                print("-" * 80)
                for item in items:
                    print(f"{item['candidate_id']:<36} {item['status']:<16} {item['kind']:<12} {item['title']}")
            return 0

        if args.skills_command == "show-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.renderers import render_markdown as _render_skill_markdown

            candidate_id = getattr(args, "candidate_id", None)
            use_json = getattr(args, "json", False)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            if use_json:
                print(candidate.model_dump_json(indent=2))
            else:
                print(_render_skill_markdown(candidate))
            return 0

        if args.skills_command == "submit-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import submit_for_review

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            submit_for_review(candidate, workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} submitted for review.")
            return 0

        if args.skills_command == "approve-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import approve

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            approve(candidate, reason=getattr(args, "reason", None), workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} approved.")
            return 0

        if args.skills_command == "reject-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import reject

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            reject(candidate, reason=getattr(args, "reason", None), workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} rejected.")
            return 0

        if args.skills_command == "archive-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import archive

            candidate_id = getattr(args, "candidate_id", None)
            candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
            archive(candidate, reason=getattr(args, "reason", None), workspace=str(config.workspace_root))
            print(f"Skill candidate {candidate_id} archived.")
            return 0

        if args.skills_command == "promote-candidate":
            from atlas_agent.skills.storage import load_candidate
            from atlas_agent.skills.approval import promote_to_library

            candidate_id = getattr(args, "candidate_id", None)
            try:
                candidate = load_candidate(candidate_id, workspace=str(config.workspace_root))
                entry = promote_to_library(candidate, workspace=str(config.workspace_root))
                print(f"Skill candidate {candidate_id} promoted to library as skill {entry.skill_id}.")
            except (FileNotFoundError, ValueError) as exc:
                print(f"Error: {exc}")
                return 2
            return 0

        if args.skills_command == "list-library":
            from atlas_agent.skills.library import list_skills as _list_library_skills

            use_json = getattr(args, "json", False)
            items = _list_library_skills(workspace=str(config.workspace_root))
            if use_json:
                print(json.dumps(items, indent=2, sort_keys=True, default=str))
            else:
                if not items:
                    print("No skills in library.")
                    return 0
                print(f"{'ID':<36} {'Kind':<12} {'Title'}")
                print("-" * 60)
                for item in items:
                    print(f"{item['skill_id']:<36} {item['kind']:<12} {item['title']}")
            return 0

        if args.skills_command == "show-library":
            from atlas_agent.skills.library import load_skill
            from atlas_agent.skills.renderers import render_skill_markdown

            skill_id = getattr(args, "skill_id", None)
            use_json = getattr(args, "json", False)
            entry = load_skill(skill_id, workspace=str(config.workspace_root))
            if use_json:
                print(entry.model_dump_json(indent=2))
            else:
                print(render_skill_markdown(entry))
            return 0
    return None

