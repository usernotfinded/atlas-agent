# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    skills/manager.py
# PURPOSE: Moves skills through their lifecycle on disk — proposed → active →
#          archived — and diffs them so a reviewer can see exactly what changed
#          before approving a rule the agent will then follow.
# DEPS:    difflib (the review diff), shutil (directory promotion)
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import difflib
import re
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

REQUIRED_METADATA_FIELDS = {
    "status": "proposed",
    "confidence": "0.40",
    "risk_level": "medium",
    "evidence": "journal evidence pending review",
    "last_updated": date.today().isoformat(),
}

SKILL_CATEGORIES = ("active", "proposed", "archived")

METADATA_RE = re.compile(r"(?ms)^## Metadata\s*\n.*?(?=^## |\Z)")


def list_skills(skills_dir: Path) -> dict[str, list[str]]:
    results = {category: [] for category in SKILL_CATEGORIES}
    for category in SKILL_CATEGORIES:
        category_dir = skills_dir / category
        if category_dir.exists():
            results[category] = sorted(
                f.name for f in category_dir.glob("*.md") if f.name != ".gitkeep"
            )
    return results


def approve_skill(skills_dir: Path, skill_name: str) -> str:
    skill_name = normalize_skill_name(skill_name)
    source = skills_dir / "proposed" / skill_name
    target = skills_dir / "active" / skill_name

    if not source.exists():
        raise FileNotFoundError(f"Proposed skill not found: {skill_name}")

    updated = improve_skill_text(
        source.read_text(encoding="utf-8"),
        default_name=source.stem,
        status="active",
    )
    source.write_text(updated, encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, target)
    return str(target)


def archive_skill(skills_dir: Path, skill_name: str) -> str:
    skill_name = normalize_skill_name(skill_name)
    source = skills_dir / "active" / skill_name
    if not source.exists():
        source = skills_dir / "proposed" / skill_name

    if not source.exists():
        raise FileNotFoundError(f"Skill not found in active or proposed: {skill_name}")

    updated = improve_skill_text(
        source.read_text(encoding="utf-8"),
        default_name=source.stem,
        status="archived",
    )
    source.write_text(updated, encoding="utf-8")
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
        updated = improve_skill_text(original, default_name=path.stem, status="proposed")
        if updated != original:
            path.write_text(updated, encoding="utf-8")
        improved.append(path)
    return improved


def improve_skill_text(
    text: str,
    *,
    default_name: str = "proposed_skill",
    status: str = "proposed",
) -> str:
    content = text.rstrip()
    if not content:
        content = f"# Skill: {default_name}\n"

    additions: list[str] = []
    for section, fallback in REQUIRED_SKILL_SECTIONS:
        if _has_skill_section(content, section):
            continue
        value = default_name if section == "Name" else fallback
        additions.append(f"## {section}\n{value}")

    if additions:
        content = content + "\n\n" + "\n\n".join(additions)
    return _upsert_metadata_block(content, default_name=default_name, status=status)


def show_skill(skills_dir: Path, skill_name: str) -> dict[str, str | dict[str, str]]:
    path = find_skill_path(skills_dir, skill_name)
    if path is None:
        raise FileNotFoundError(f"Skill not found: {skill_name}")
    content = path.read_text(encoding="utf-8")
    return {
        "path": str(path),
        "status": _category_from_path(path),
        "metadata": extract_skill_metadata(content),
        "content": content,
    }


def diff_skill(skills_dir: Path, skill_name: str) -> list[str]:
    skill_name = normalize_skill_name(skill_name)
    proposed_path = skills_dir / "proposed" / skill_name
    active_path = skills_dir / "active" / skill_name
    if not proposed_path.exists() or not active_path.exists():
        missing: list[str] = []
        if not proposed_path.exists():
            missing.append(str(proposed_path))
        if not active_path.exists():
            missing.append(str(active_path))
        raise FileNotFoundError("Missing counterpart skill file(s): " + ", ".join(missing))
    proposed_text = proposed_path.read_text(encoding="utf-8").splitlines()
    active_text = active_path.read_text(encoding="utf-8").splitlines()
    return list(
        difflib.unified_diff(
            active_text,
            proposed_text,
            fromfile=str(active_path),
            tofile=str(proposed_path),
            lineterm="",
        )
    )


def find_skill_path(skills_dir: Path, skill_name: str) -> Path | None:
    name = normalize_skill_name(skill_name)
    for category in SKILL_CATEGORIES:
        path = skills_dir / category / name
        if path.exists():
            return path
    return None


def normalize_skill_name(skill_name: str) -> str:
    return skill_name if skill_name.endswith(".md") else f"{skill_name}.md"


def extract_skill_metadata(text: str) -> dict[str, str]:
    metadata = REQUIRED_METADATA_FIELDS.copy()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("-"):
            continue
        key_value = stripped.lstrip("- ").split(":", 1)
        if len(key_value) != 2:
            continue
        key = key_value[0].strip().lower().replace(" ", "_")
        value = key_value[1].strip()
        if key in metadata and value:
            metadata[key] = value
    metadata["last_updated"] = metadata.get("last_updated") or date.today().isoformat()
    return metadata


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


def _upsert_metadata_block(content: str, *, default_name: str, status: str) -> str:
    metadata = extract_skill_metadata(content)
    metadata["status"] = status
    metadata["last_updated"] = date.today().isoformat()
    if not metadata.get("evidence"):
        metadata["evidence"] = f"See journal and reflection evidence for {default_name}."
    block_lines = [
        "## Metadata",
        f"- status: {metadata['status']}",
        f"- confidence: {metadata['confidence']}",
        f"- risk_level: {metadata['risk_level']}",
        f"- evidence: {metadata['evidence']}",
        f"- last_updated: {metadata['last_updated']}",
    ]
    block = "\n".join(block_lines)
    if METADATA_RE.search(content):
        updated = METADATA_RE.sub(block + "\n", content)
    else:
        updated = content.rstrip() + "\n\n" + block + "\n"
    return updated.rstrip() + "\n"


def _category_from_path(path: Path) -> str:
    if path.parent.name in SKILL_CATEGORIES:
        return path.parent.name
    return "unknown"
