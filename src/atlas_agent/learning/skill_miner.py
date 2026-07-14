# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    learning/skill_miner.py
# PURPOSE: Mines reusable skills from the trade journal — or, today, honestly
#          reports that it cannot.
# DEPS:    stdlib only
#
# NOT IMPLEMENTED: real mining requires an LLM pass over the journal, which does not
#          exist yet. Until it does, mine_skills_from_journal() returns NOTHING.
#          It deliberately does not fabricate a plausible-looking proposal, because a
#          skill is a rule the agent will follow and its "evidence" field is a claim
#          about the user's own trading history. An invented one would be believed —
#          it looks exactly like a real one. This is the same rule the rest of the
#          learning domain already states: "No fake insights are invented."
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import datetime
from pathlib import Path


# ==============================================================================
# SKILL MINING
# ==============================================================================

def mine_skills_from_journal(memory_dir: Path) -> list[dict]:
    """Mine candidate skills from the trade journal.

    Args:
        memory_dir: the workspace memory directory.

    Returns:
        Always an empty list: journal mining is not implemented (see the module
        header). Callers already handle this — `atlas skills propose` reports
        "No new skills identified from journal.", which is the truth.
    """
    return []


# ==============================================================================
# SKILL PERSISTENCE
# ==============================================================================

def save_proposed_skill(skills_dir: Path, skill: dict) -> Path:
    proposed_dir = skills_dir / "proposed"
    proposed_dir.mkdir(parents=True, exist_ok=True)
    
    path = proposed_dir / f"{skill['name']}.md"
    content = f"""# Skill: {skill['name']}

- Purpose: {skill['purpose']}
- When to use: {skill['when_to_use']}
- Inputs: {skill['inputs']}
- Outputs: {skill['outputs']}
- Risk Constraints: Standard RiskManager checks
- Failure Modes: Missing data, low confidence
- Evidence: {skill['evidence']}
- Last Updated: {datetime.date.today().isoformat()}
- Confidence Level: Inferred
- Owner: Atlas Agent

## Metadata
- status: proposed
- confidence: 0.40
- risk_level: medium
- evidence: {skill['evidence']}
- last_updated: {datetime.date.today().isoformat()}
"""
    path.write_text(content, encoding="utf-8")
    return path
