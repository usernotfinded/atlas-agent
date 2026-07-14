# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/__init__.py
# PURPOSE: Public surface of the learning domain. The agent proposes lessons drawn
#          from its own journal — but every suggestion is ADVISORY and requires an
#          explicit human accept before it can influence anything.
# DEPS:    learning.loop, learning.models, learning.storage, learning.approval
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.learning.loop import run_learning_cycle
from atlas_agent.learning.reflections import generate_reflection
from atlas_agent.learning.user_model import load_user_model, save_user_model
from atlas_agent.learning.conversation_memory import (
    ingest_conversation,
    rebuild_search_index,
    search_memory,
)
from atlas_agent.learning.models import (
    LearningSuggestion,
    SuggestionStatus,
    SuggestionProvenance,
    SuggestionAudit,
)
from atlas_agent.learning.storage import (
    save_suggestion,
    load_suggestion,
    list_suggestions,
    delete_suggestion,
)
from atlas_agent.learning.generator import (
    generate_suggestion_from_reflection,
    generate_suggestion_from_skill,
    generate_suggestion_from_input,
)
from atlas_agent.learning.approval import (
    submit_for_review,
    accept,
    reject,
    archive,
)
from atlas_agent.learning.renderers import (
    render_markdown,
    render_json_string,
)

__all__ = [
    "run_learning_cycle",
    "generate_reflection",
    "load_user_model",
    "save_user_model",
    "ingest_conversation",
    "rebuild_search_index",
    "search_memory",
    "LearningSuggestion",
    "SuggestionStatus",
    "SuggestionProvenance",
    "SuggestionAudit",
    "save_suggestion",
    "load_suggestion",
    "list_suggestions",
    "delete_suggestion",
    "generate_suggestion_from_reflection",
    "generate_suggestion_from_skill",
    "generate_suggestion_from_input",
    "submit_for_review",
    "accept",
    "reject",
    "archive",
    "render_markdown",
    "render_json_string",
]
