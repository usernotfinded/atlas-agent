# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    reflection/__init__.py
# PURPOSE: Public surface of the reflection domain. Same shape as learning/ and
#          skills/: generate → review → approve. All three keep the agent's
#          self-analysis behind a human gate.
# DEPS:    reflection.generator, reflection.approval, reflection.storage
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.reflection.approval import approve, archive, reject, submit_for_review
from atlas_agent.reflection.generator import generate_reflection
from atlas_agent.reflection.models import ReflectionArtifact, ReflectionStatus
from atlas_agent.reflection.renderers import render_markdown
from atlas_agent.reflection.storage import delete_artifact, list_artifacts, load_artifact, save_artifact

__all__ = [
    "approve",
    "archive",
    "delete_artifact",
    "generate_reflection",
    "list_artifacts",
    "load_artifact",
    "reject",
    "render_markdown",
    "save_artifact",
    "submit_for_review",
    "ReflectionArtifact",
    "ReflectionStatus",
]
