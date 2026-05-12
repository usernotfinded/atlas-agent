from typing import List, Tuple, Optional
from atlas_agent.setup.state import WizardState
from atlas_agent.ui.banner import ATLAS_ASCII_BANNER, ATLAS_TAGLINE

def render_wizard_screen(
    state: WizardState,
    current_step: str,
    choices: List[Tuple[str, str]],
    current_index: int,
    input_value: str = "",
    title: str = "",
    is_password: bool = False
) -> List[Tuple[str, str]]:
    """Pure function to render the wizard screen state."""
    lines = []
    
    # Prepend the banner and tagline
    lines.append(("class:normal", ATLAS_ASCII_BANNER))
    lines.append(("class:normal", f"\n{ATLAS_TAGLINE}\n\n"))
    
    lines.append(("class:title", "Atlas Agent Setup\n\n"))

    # Selected so far summary
    summary = get_summary_lines(state, current_step)
    if summary:
        lines.extend(summary)

    # Current step title and instructions
    lines.append(("class:title", f"{title}\n"))
    
    if choices:
        lines.append(("class:muted", "  ↑↓ navigate   ENTER/SPACE select   ESC cancel   BACKSPACE back\n\n"))
        for i, (val, label) in enumerate(choices):
            is_selected = (i == current_index)
            prefix = "→ " if is_selected else "  "
            bullet = "(●)" if is_selected else "(○)"
            style = "class:selected" if is_selected else "class:normal"
            lines.append((style, f"{prefix}{bullet} {label}\n"))
    else:
        # Input step
        lines.append(("class:muted", "  ENTER confirm   ESC cancel   BACKSPACE back (if empty)\n\n"))
        display_value = "*" * len(input_value) if is_password else input_value
        lines.append(("class:normal", f"> {display_value}"))
        lines.append(("class:selected", "█\n")) # Cursor placeholder

    return lines

def get_summary_lines(state: WizardState, current_step: str) -> List[Tuple[str, str]]:
    steps_order = [
        "setup_mode",
        "provider",
        "google_api_mode",
        "google_auth_method",
        "custom_endpoint",
        "api_key",
        "model",
        "messaging",
        "workspace_path",
        "trust_mode",
        "broker_mode",
        "update_channel",
    ]
    
    relevant_steps = []
    for step in steps_order:
        if step == current_step:
            break
        # Logic to skip irrelevant steps in summary
        if step in {"google_api_mode", "google_auth_method"} and state.provider != "google":
            continue
        if step == "custom_endpoint" and state.provider not in ["custom", "openai-compatible", "lmstudio"]:
            continue
        if step == "api_key":
            if state.provider in ["null", "local_command"]:
                continue
            if state.provider == "google" and state.google_auth_method == "oauth_adc":
                continue
            relevant_steps.append(step)
            continue
            
        if state.setup_mode == "quick" and step in ["workspace_path", "trust_mode", "broker_mode", "update_channel"]:
            continue
        relevant_steps.append(step)

    if not relevant_steps:
        return []

    lines = [("class:normal", "Selected so far:\n")]
    for step in relevant_steps:
        if step == "api_key":
            lines.append(("class:muted", "  API Key: "))
            status = "configured" if state.credentials_configured else "missing"
            lines.append(("class:normal", f"{status}\n"))
            continue
            
        val = getattr(state, step)
        if val:
            label = step.replace("_", " ").title()
            lines.append(("class:muted", f"  {label}: "))
            lines.append(("class:normal", f"{val}\n"))
    lines.append(("class:normal", "\n"))
    return lines
