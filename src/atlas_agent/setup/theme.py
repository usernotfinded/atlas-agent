# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    setup/theme.py
# PURPOSE: The colour palette for the interactive wizard.
# DEPS:    prompt_toolkit
# ==============================================================================

# --- IMPORTS ---
from prompt_toolkit.styles import Style


# --- CONFIGURATIONS & CONSTANTS ---

# Atlas Agent electric blue theme
# primary: #1EA7FF
# accent: #00C2FF
# background: #0B1220
# panel: #111A2B
# primary text: #E6EDF7
# muted text: #94A3B8

atlas_theme = Style.from_dict({
    "title": "#1EA7FF bold",
    "muted": "#94A3B8",
    "selected": "#1EA7FF bold",
    "normal": "#E6EDF7",
})
