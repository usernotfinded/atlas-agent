from __future__ import annotations

from pathlib import Path
from typing import Any


_REQUIRED_SAFETY_SENTENCE = (
    "User discipline cannot override Atlas risk gates, approval queues, kill switch, "
    "audit logging, broker sync checks, reference price requirements, or live-trading safeguards."
)

_FORBIDDEN_PATTERNS = {
    "ignore risk limits",
    "bypass risk manager",
    "bypass kill switch",
    "disable audit",
    "hide trades",
    "trade without approval",
    "always trade",
    "use maximum leverage",
    "ignore reference price",
    "ignore broker sync",
    "guaranteed profit",
    "risk-free",
    "make money",
    "production-grade live trading",
}

_DISCIPLINE_SECTIONS = (
    "Decision temperament",
    "Reasoning style",
    "Communication style",
    "Risk posture",
    "Uncertainty handling",
    "No-trade bias",
    "Forbidden overrides",
)


class DisciplineNotConfiguredError(Exception):
    """Raised when a user discipline profile is required but missing or invalid."""

    def __str__(self) -> str:
        return (
            "Atlas Discipline Profile is not configured. "
            "Run `atlas discipline setup` before starting agentic trading workflows."
        )


class InvalidDisciplineProfileError(Exception):
    """Raised when a user discipline profile contains forbidden language or is malformed."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            "Discipline profile is invalid: " + "; ".join(errors)
        )


def default_discipline_text() -> str:
    """Return the built-in default discipline markdown.

    This is a non-operational template/skeleton for manual setup or generation.
    It must NOT be used as a runtime fallback for agentic workflows.
    """
    path = Path(__file__).with_suffix("").parent / "default_discipline.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Fallback if file is missing
    return (
        "# Atlas User Discipline Profile\n\n"
        "## Decision temperament\n\n"
        "Cautious and evidence-seeking.\n\n"
        "## Reasoning style\n\n"
        "Step-by-step and transparent.\n\n"
        "## Communication style\n\n"
        "Concise, structured, and respectful.\n\n"
        "## Risk posture\n\n"
        "Conservative.\n\n"
        "## Uncertainty handling\n\n"
        "Explicitly state confidence levels.\n\n"
        "## No-trade bias\n\n"
        "Default to no action unless the case is compelling.\n\n"
        "## Forbidden overrides\n\n"
        f"{_REQUIRED_SAFETY_SENTENCE}\n"
    )


def discipline_path(workspace_root: str | Path = ".") -> Path:
    """Return the path to the user discipline file for a workspace."""
    return Path(workspace_root) / ".atlas" / "discipline.md"


def load_user_discipline(workspace_root: str | Path = ".") -> str | None:
    """Load the user discipline markdown if it exists and is valid."""
    path = discipline_path(workspace_root)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    ok, errors = validate_discipline_text(text)
    if not ok:
        return None
    return text


def require_user_discipline(workspace_root: str | Path = ".") -> str:
    """Require a valid user discipline profile. Raise if missing or invalid.

    Never fall back to default_discipline_text().
    """
    path = discipline_path(workspace_root)
    if not path.exists():
        raise DisciplineNotConfiguredError()
    text = path.read_text(encoding="utf-8")
    ok, errors = validate_discipline_text(text)
    if not ok:
        raise InvalidDisciplineProfileError(errors)
    return text


def write_user_discipline(workspace_root: str | Path, content: str) -> None:
    """Write discipline markdown after validation."""
    path = discipline_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_discipline_generation_prompt(user_text: str) -> str:
    """Build a prompt that asks the LLM to turn freeform user input into structured discipline."""
    sections_text = "\n".join(f"- {s}" for s in _DISCIPLINE_SECTIONS)
    return (
        "You are Atlas Agent's discipline formatter. "
        "Convert the user's freeform description into a structured discipline profile.\n\n"
        "The profile must be valid Markdown with these exact sections:\n"
        f"{sections_text}\n\n"
        "Rules:\n"
        "- Each section should be 2-6 sentences.\n"
        "- Tone must remain cautious, broker-neutral, and non-promotional.\n"
        f"- The final section must contain this exact sentence:\n  {_REQUIRED_SAFETY_SENTENCE}\n"
        "- Do not include API keys, passwords, or secrets.\n"
        "- Do not include profit claims or guarantees.\n\n"
        "User description:\n"
        f"{user_text}\n\n"
        "Output only the Markdown discipline profile, no extra commentary."
    )


def validate_discipline_text(text: str) -> tuple[bool, list[str]]:
    """Validate discipline text for forbidden override language and required safety sentence."""
    errors: list[str] = []
    lower = text.lower()

    # Check for forbidden patterns
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in lower:
            errors.append(f"Forbidden phrase detected: '{pattern}'")

    # Check for required safety sentence
    if _REQUIRED_SAFETY_SENTENCE not in text:
        errors.append("Missing required safety sentence in Forbidden overrides section.")

    # Check for required sections
    for section in _DISCIPLINE_SECTIONS:
        if f"## {section}" not in text:
            errors.append(f"Missing section: {section}")

    return (not errors, errors)


def sanitize_discipline_text(text: str) -> str:
    """Remove or redact potentially dangerous content from discipline text."""
    lines = text.splitlines()
    result: list[str] = []
    for line in lines:
        lower = line.lower()
        # Skip lines that contain forbidden patterns
        if any(pattern in lower for pattern in _FORBIDDEN_PATTERNS):
            result.append("<!-- Line removed during sanitization -->")
        else:
            result.append(line)
    return "\n".join(result)


def discipline_status(workspace_root: str | Path = ".") -> dict[str, Any]:
    """Return the current discipline status for a workspace."""
    path = discipline_path(workspace_root)
    if not path.exists():
        return {"configured": False, "valid": False, "path": str(path), "errors": []}
    text = path.read_text(encoding="utf-8")
    ok, errors = validate_discipline_text(text)
    return {"configured": True, "valid": ok, "path": str(path), "errors": errors}
