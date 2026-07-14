# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    __init__.py
# PURPOSE: Package root. Holds the single source of truth for the version string.
# DEPS:    none — kept import-free so that `import atlas_agent` stays free of any
#          side effect, and the release checkers can read __version__ cheaply.
# ==============================================================================

"""Atlas Agent: safe-by-default AI trading framework."""

# Bumped by the release cutover, and cross-checked against CHANGELOG.md and the
# git tag by the release-gate checkers. Do not edit by hand outside a cutover.
__version__ = "0.6.26"
