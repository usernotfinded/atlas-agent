from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class UserModel:
    profile: str
    preferences: str
    trading_style: str


def load_user_model(memory_dir: Path) -> UserModel:
    profile_path = memory_dir / "user_profile.md"
    pref_path = memory_dir / "preferences.md"
    style_path = memory_dir / "trading_style.md"

    profile = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    preferences = pref_path.read_text(encoding="utf-8") if pref_path.exists() else ""
    trading_style = style_path.read_text(encoding="utf-8") if style_path.exists() else ""

    return UserModel(profile=profile, preferences=preferences, trading_style=trading_style)


def save_user_model(memory_dir: Path, model: UserModel) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "user_profile.md").write_text(model.profile, encoding="utf-8")
    (memory_dir / "preferences.md").write_text(model.preferences, encoding="utf-8")
    (memory_dir / "trading_style.md").write_text(model.trading_style, encoding="utf-8")


def remember_user_note(memory_dir: Path, text: str) -> Path:
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / "preferences.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# User Preferences\n"
    if "## Remembered Notes" not in existing:
        existing = existing.rstrip() + "\n\n## Remembered Notes\n"
    entry = f"- {date.today().isoformat()}: {text.strip()}\n"
    path.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")
    return path


def format_user_model_summary(memory_dir: Path) -> str:
    model = load_user_model(memory_dir)
    if not any((model.profile.strip(), model.preferences.strip(), model.trading_style.strip())):
        return (
            "No user model exists yet. Add one with "
            'atlas user remember "..."'
        )
    return "\n".join(
        (
            "Atlas User Model",
            _section_summary("Profile", model.profile),
            _section_summary("Preferences", model.preferences),
            _section_summary("Trading Style", model.trading_style),
        )
    )


def _section_summary(title: str, content: str) -> str:
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        return f"{title}: not set"
    return f"{title}: {'; '.join(lines[:4])}"
