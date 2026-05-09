import pytest
from atlas_agent.setup.state import WizardState
from atlas_agent.setup.renderer import render_wizard_screen, get_summary_lines
from atlas_agent.setup.wizard_ui import WizardApplication

def test_wizard_does_not_append_previous_steps():
    """Verify renderer output only contains current step title and choices."""
    state = WizardState()
    choices = [("a", "Alpha"), ("b", "Beta")]
    rendered = render_wizard_screen(state, "setup_mode", choices, 0, title="Step 1")
    
    # Convert FormattedText to plain text
    text = "".join(t[1] for t in rendered)
    
    assert "Step 1" in text
    assert "Alpha" in text
    assert "Beta" in text
    assert "Selected so far" not in text # No summary for first step

def test_step_render_contains_only_current_choices():
    state = WizardState(setup_mode="quick", provider="anthropic")
    choices = [("m1", "Model 1")]
    rendered = render_wizard_screen(state, "model", choices, 0, title="Select Model")
    
    text = "".join(t[1] for t in rendered)
    assert "Select Model" in text
    assert "Model 1" in text
    # Should NOT contain setup_mode choices
    assert "Quick setup" not in text

def test_selected_so_far_summary_is_non_interactive():
    state = WizardState(setup_mode="quick", provider="anthropic")
    summary = get_summary_lines(state, "model")
    text = "".join(t[1] for t in summary)
    
    assert "Selected so far:" in text
    assert "Setup Mode: quick" in text
    assert "Provider: anthropic" in text
    assert "(●)" not in text # Not interactive choices

def test_back_uses_state_not_terminal_history():
    state = WizardState()
    app = WizardApplication(state)
    app.current_step = "provider"
    app.history = ["setup_mode"]
    
    app.back_step()
    assert app.current_step == "setup_mode"
    assert app.history == []

def test_input_step_rendering():
    state = WizardState(provider="custom")
    rendered = render_wizard_screen(state, "custom_endpoint", [], 0, input_value="http://localhost", title="Custom Endpoint")
    text = "".join(t[1] for t in rendered)
    
    assert "Custom Endpoint" in text
    assert "http://localhost" in text
    assert "> " in text
    assert "█" in text # Cursor
