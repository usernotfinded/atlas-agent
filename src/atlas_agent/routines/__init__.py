# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    routines/__init__.py
# PURPOSE: Public surface of the routines domain: the scheduled, unattended runs.
# DEPS:    routines.engine, routines.routine_result
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.routines.engine import ROUTINE_NAMES, run_routine
from atlas_agent.routines.routine_result import RoutineResult


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = ["ROUTINE_NAMES", "RoutineResult", "run_routine"]

