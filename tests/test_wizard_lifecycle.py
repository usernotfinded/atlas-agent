# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_wizard_lifecycle.py
# PURPOSE: Verifies wizard lifecycle behavior and regression expectations.
# DEPS:    pytest, atlas_agent.
# ==============================================================================

# --- IMPORTS ---

import pytest
from atlas_agent.setup.state import WizardState
from atlas_agent.setup.renderer import render_wizard_screen, get_summary_lines
from atlas_agent.setup.wizard_ui import WizardApplication

# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

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

def test_wizard_renderer_includes_banner():
    state = WizardState()
    choices = [("a", "Alpha")]
    rendered = render_wizard_screen(state, "setup_mode", choices, 0, title="Setup")
    text = "".join(t[1] for t in rendered)
    
    assert "___ _____ _      _   ___" in text
    assert "Atlas Agent is a broker-neutral supervised trading workspace." in text
    assert "Atlas Agent Setup" in text

def test_wizard_renderer_keeps_banner_across_steps():
    state = WizardState()
    
    # Step 1
    rendered1 = render_wizard_screen(state, "setup_mode", [("q", "Quick")], 0, title="Step 1")
    text1 = "".join(t[1] for t in rendered1)
    assert "___ _____ _      _   ___" in text1
    assert "Step 1" in text1
    
    # Step 2
    state.setup_mode = "quick"
    rendered2 = render_wizard_screen(state, "provider", [("p", "Provider")], 0, title="Step 2")
    text2 = "".join(t[1] for t in rendered2)
    assert "___ _____ _      _   ___" in text2
    assert "Step 2" in text2
    assert "Quick" not in text2 # Choices from previous step not in current choices

def test_prompt_toolkit_filters_are_condition_instances():
    from prompt_toolkit.key_binding import KeyBindings
    from unittest.mock import patch
    
    state = WizardState()
    app = WizardApplication(state)
    
    # We want to instantiate the Application in `run` but not actually run it,
    # or just run it with a mock that exits immediately to ensure key bindings
    # are built successfully without TypeError.
    
    # Alternatively, we can mock `Application.run` to just return False,
    # ensuring the instantiation `app = Application(...)` succeeds.
    with patch("prompt_toolkit.Application.run", return_value=False):
        try:
            app.run()
        except TypeError as e:
            pytest.fail(f"TypeError raised during Application instantiation, likely a filter issue: {e}")
