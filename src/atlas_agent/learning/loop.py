from __future__ import annotations

import datetime
from pathlib import Path

from atlas_agent.events.log import EventLogger
from atlas_agent.learning.reflections import generate_reflection
from atlas_agent.learning.skill_miner import mine_skills_from_journal, save_proposed_skill
from atlas_agent.learning.user_model import load_user_model

def run_learning_cycle(
    memory_dir: Path,
    reports_dir: Path,
    skills_dir: Path,
    *,
    event_logger: EventLogger | None = None,
    run_id: str | None = None,
    command: str = "atlas agent learn",
    mode: str = "paper",
) -> str:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M")
    learning_dir = reports_dir / "learning"
    learning_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load context
    user_model = load_user_model(memory_dir)
    
    # 2. Mine skills
    proposed_skills = mine_skills_from_journal(memory_dir)
    saved_paths = []
    for skill in proposed_skills:
        saved_paths.append(save_proposed_skill(skills_dir, skill))
        if event_logger is not None and run_id is not None:
            event_logger.write(
                "skill_proposed",
                run_id=run_id,
                command=command,
                mode=mode,
                payload={"skill": skill.get("name", "unknown")},
            )
        
    # 3. Generate reflection
    reflection_path = generate_reflection(
        memory_dir,
        reports_dir,
        event_logger=event_logger,
        run_id=run_id,
        command=command,
        mode=mode,
    )
    
    # 4. Write learning report
    report_path = learning_dir / f"{timestamp}-learning-cycle.md"
    report_content = f"""# Learning Cycle Report: {timestamp}

- User Profile Status: Loaded
- Proposed Skills: {len(saved_paths)}
- Reflection Generated: {reflection_path.name}

## Proposed Skill Paths
"""
    for p in saved_paths:
        report_content += f"- {p.relative_to(skills_dir.parent)}\n"
        
    report_path.write_text(report_content, encoding="utf-8")
    return str(report_path)
