import ast
from pathlib import Path

def test_inline_selector_renders_without_dialog_box():
    """Verify that no modal or dialog boxes are imported or used in the wizard."""
    wizard_path = Path("src/atlas_agent/setup/wizard.py")
    content = wizard_path.read_text(encoding="utf-8")
    
    tree = ast.parse(content)
    
    banned_names = {"radiolist_dialog", "button_dialog", "input_dialog", "yes_no_dialog"}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name not in banned_names, f"Banned modal dialog import found: {alias.name}"
        elif isinstance(node, ast.Name):
            assert node.id not in banned_names, f"Banned modal dialog usage found: {node.id}"
            
    # Ensure our custom inline selector is imported and used
    assert "WizardApplication" in content, "WizardApplication must be used"
