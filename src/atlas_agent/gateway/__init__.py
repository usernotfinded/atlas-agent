# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    gateway/__init__.py
# PURPOSE: Package marker for the remote control plane. Deliberately empty: the
#          gateway subpackages (telegram/) are imported explicitly by the callers
#          that need them, so a plain `import atlas_agent` never drags a remote
#          surface — or its optional dependencies — into the process.
# DEPS:    none
# ==============================================================================

from __future__ import annotations
