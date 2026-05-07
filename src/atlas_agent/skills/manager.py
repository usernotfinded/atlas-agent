from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path


REQUIRED_SKILL_SECTIONS = (
    ("Name", "Unnamed proposed skill."),
    ("Purpose", "State the behavior this skill should improve."),
    ("When to use", "Describe the trading context that should trigger this skill."),
    ("Inputs", "List memory files, reports, market data, or user inputs required."),
    ("Output format", "Describe the expected Markdown or structured output."),
    ("Risk constraints", "Do not bypass RiskManager, approval gates, broker adapters, or the kill switch."),
    ("Failure modes", "List missing data, stale context, low confidence, and safety refusal cases."),
    ("Evidence/source journal entries", "Reference the journal, report, or reflection that motivated the skill."),
    ("Last updated", date.today().isoformat()),
    ("Confidence level", "Draft until reviewed and approved by the user."),
    ("Owner", "Atlas Agent"),
)


def list_skills(skills_dir: Path) -> dict[str, list[str]]:
    results = {"active": [], "proposed": [], "archived": []}
    for category in results.keys():
        category_dir = skills_dir / category
        if category_dir.exists():
            results[category] = [f.name for f in category_dir.glob("*.md")]
    return results


def approve_skill(skills_dir: Path, skill_name: str) -> str:
    if not skill_name.endswith(".md"):
        skill_name += ".md"

    source = skills_dir / "proposed" / skill_name
    target = skills_dir / "active" / skill_name

    if not source.exists():
        raise FileNotFoundError(f"Proposed skill not found: {skill_name}")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, target)
    return str(target)


def archive_skill(skills_dir: Path, skill_name: str) -> str:
    if not skill_name.endswith(".md"):
        skill_name += ".md"

    source = skills_dir / "active" / skill_name
    if not source.exists():
        source = skills_dir / "proposed" / skill_name

    if not source.exists():
        raise FileNotFoundError(f"Skill not found in active or proposed: {skill_name}")

    target = skills_dir / "archived" / skill_name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, target)
    return str(target)


def improve_proposed_skills(skills_dir: Path) -> list[Path]:
    proposed_dir = skills_dir / "proposed"
    if not proposed_dir.exists():
        return []

    improved: list[Path] = []
    for path in sorted(proposed_dir.glob("*.md")):
        if path.name == ".gitkeep":
            continue
        original = path.read_text(encoding="utf-8")
        updated = improve_skill_text(original, default_name=path.stem)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
        improved.append(path)
    return improved


def improve_skill_text(text: str, *, default_name: str = "proposed_skill") -> str:
    content = text.rstrip()
    if not content:
        content = f"# Skill: {default_name}\n"

    additions: list[str] = []
    for section, fallback in REQUIRED_SKILL_SECTIONS:
        if _has_skill_section(content, section):
            continue
        value = default_name if section == "Name" else fallback
        additions.append(f"## {section}\n{value}")

    if not additions:
        return content + "\n"
    return content + "\n\n" + "\n\n".join(additions) + "\n"


def _has_skill_section(text: str, section: str) -> bool:
    section_lower = section.lower()
    for raw_line in text.splitlines():
        line = raw_line.strip().lower()
        if line.startswith("#") and line.lstrip("#").strip().rstrip(":") == section_lower:
            return True
        if line.startswith("-") and line.lstrip("- ").split(":", 1)[0].strip() == section_lower:
            return True
    aliases = {
        "output format": ("outputs",),
        "evidence/source journal entries": ("evidence", "source journal entries"),
        "risk constraints": ("risk constraints", "risk constraints"),
        "failure modes": ("failure modes",),
    }
    for alias in aliases.get(section_lower, ()):
        for raw_line in text.splitlines():
            line = raw_line.strip().lower()
            if line.startswith("-") and line.lstrip("- ").split(":", 1)[0].strip() == alias:
                return True
    return False
