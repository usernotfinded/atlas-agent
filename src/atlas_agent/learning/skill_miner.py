from __future__ import annotations

import datetime
from pathlib import Path


def mine_skills_from_journal(memory_dir: Path) -> list[dict]:
    """Placeholder for mining skills from journal experience."""
    journal_path = memory_dir / "trade_journal.md"
    if not journal_path.exists():
        return []
    
    # Real implementation would use LLM to analyze journal.
    # For MVP, we'll return a static proposed skill if journal is non-empty.
    content = journal_path.read_text(encoding="utf-8")
    if len(content) > 50:
        return [
            {
                "name": "journal_pattern_recognition",
                "purpose": "Identify recurring trade patterns from journal history.",
                "when_to_use": "During pre-market routine or weekly review.",
                "inputs": "trade_journal.md",
                "outputs": "pattern_report.md",
                "evidence": "Observed multiple similar entries in trade_journal.md",
            }
        ]
    return []

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
