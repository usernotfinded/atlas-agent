from __future__ import annotations

import datetime
from pathlib import Path

from atlas_agent.learning.reflections import generate_reflection
from atlas_agent.learning.skill_miner import mine_skills_from_journal, save_proposed_skill
from atlas_agent.learning.user_model import load_user_model

def run_learning_cycle(memory_dir: Path, reports_dir: Path, skills_dir: Path) -> str:
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
        
    # 3. Generate reflection
    reflection_path = generate_reflection(memory_dir, reports_dir)
    
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
