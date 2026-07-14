# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    skills/__init__.py
# PURPOSE: Public surface of the skills domain. A "skill" is a reusable rule the
#          agent proposes for itself; PROMOTION into the active library is the gate,
#          and it requires a human.
# DEPS:    skills.manager, skills.models, skills.storage, skills.library
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.skills.manager import (
    approve_skill,
    archive_skill,
    diff_skill,
    find_skill_path,
    extract_skill_metadata,
    improve_proposed_skills,
    improve_skill_text,
    list_skills,
    show_skill,
)
from atlas_agent.skills.models import (
    SkillCandidate,
    SkillCandidateStatus,
    SkillLibraryEntry,
    SkillProvenance,
    SkillAudit,
)
from atlas_agent.skills.storage import (
    save_candidate,
    load_candidate,
    list_candidates,
    delete_candidate,
)
from atlas_agent.skills.library import (
    save_skill,
    load_skill,
    list_skills as list_library_skills,
    delete_skill,
)
from atlas_agent.skills.generator import (
    generate_candidate_from_reflection,
    generate_candidate_from_input,
)
from atlas_agent.skills.approval import (
    submit_for_review,
    approve,
    reject,
    archive,
    promote_to_library,
)
from atlas_agent.skills.renderers import (
    render_markdown,
    render_json_string,
    render_skill_markdown,
    render_skill_json_string,
)

__all__ = [
    "list_skills",
    "approve_skill",
    "archive_skill",
    "show_skill",
    "diff_skill",
    "find_skill_path",
    "extract_skill_metadata",
    "improve_proposed_skills",
    "improve_skill_text",
    "SkillCandidate",
    "SkillCandidateStatus",
    "SkillLibraryEntry",
    "SkillProvenance",
    "SkillAudit",
    "save_candidate",
    "load_candidate",
    "list_candidates",
    "delete_candidate",
    "save_skill",
    "load_skill",
    "list_library_skills",
    "delete_skill",
    "generate_candidate_from_reflection",
    "generate_candidate_from_input",
    "submit_for_review",
    "approve",
    "reject",
    "archive",
    "promote_to_library",
    "render_markdown",
    "render_json_string",
    "render_skill_markdown",
    "render_skill_json_string",
]
