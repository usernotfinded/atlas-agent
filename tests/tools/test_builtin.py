import pytest
from atlas_agent.tools.registry import ToolRegistry
from atlas_agent.tools.builtin import BUILTIN_TOOLS

def test_all_tools_register_successfully():
    """
    Test that all 49 built-in tools instantiate correctly as Pydantic models
    and pass the ToolRegistry signature validation.
    This fulfills the PR 1 test criteria: "Pydantic schema validation for all 49 tools".
    """
    registry = ToolRegistry()
    
    # Check we actually have 49 tools
    assert len(BUILTIN_TOOLS) == 49
    
    for tool_spec in BUILTIN_TOOLS:
        # If the Pydantic model is invalid, it would have raised an error on instantiation in builtin.py.
        # Here we also ensure they pass signature validation when registering.
        try:
            registry.register(tool_spec)
        except ValueError as e:
            pytest.fail(f"Failed to register tool {tool_spec.name}: {str(e)}")

    assert len(registry.list_tools()) == 49
