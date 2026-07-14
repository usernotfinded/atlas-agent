# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    events/__init__.py
# PURPOSE: Public surface of the events domain — write the trail, read it back,
#          and audit it.
# DEPS:    events.log, events.schema, events.doctor
# ==============================================================================

# --- IMPORTS ---
from atlas_agent.events.doctor import EventDoctorResult, diagnose_events
from atlas_agent.events.log import (
    EventLogger,
    generate_run_id,
    latest_event_file,
    list_event_files,
    read_event_file,
    read_recent_events,
)
from atlas_agent.events.schema import KNOWN_EVENT_TYPES, REQUIRED_EVENT_FIELDS


# ==============================================================================
# PUBLIC API
# ==============================================================================

__all__ = [
    "EventDoctorResult",
    "EventLogger",
    "KNOWN_EVENT_TYPES",
    "REQUIRED_EVENT_FIELDS",
    "diagnose_events",
    "generate_run_id",
    "latest_event_file",
    "list_event_files",
    "read_event_file",
    "read_recent_events",
]
