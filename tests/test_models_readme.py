import pytest
from pathlib import Path
from unittest.mock import patch

from atlas_agent.leaderboard.roster import update_readme_roster

def test_update_readme_roster_success(tmp_path, monkeypatch):
    readme_path = tmp_path / "README.md"
    content = """# My README
Some text.

<!-- ATLAS_MODEL_ROSTER_START -->
<!-- ATLAS_MODEL_ROSTER_END -->

More text.
"""
    readme_path.write_text(content)
    
    # We patch Path to return our temp file when looking for README.md
    original_path = Path
    
    class MockPath(type(Path())):
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "README.md":
                return type(readme_path)(readme_path)
            return original_path(*args, **kwargs)
            
    with patch("atlas_agent.leaderboard.roster.Path", MockPath):
        update_readme_roster()
        
    new_content = readme_path.read_text()
    assert "<!-- ATLAS_MODEL_ROSTER_START -->" in new_content
    assert "<!-- ATLAS_MODEL_ROSTER_END -->" in new_content
    assert "| Rank | Model | Score |" in new_content
    assert "Claude Opus 4.7" in new_content

def test_update_readme_roster_missing_markers(tmp_path, monkeypatch):
    readme_path = tmp_path / "README.md"
    readme_path.write_text("No markers here.")
    
    original_path = Path
    
    class MockPath(type(Path())):
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "README.md":
                return type(readme_path)(readme_path)
            return original_path(*args, **kwargs)
            
    with patch("atlas_agent.leaderboard.roster.Path", MockPath):
        with pytest.raises(ValueError, match="Missing <!-- ATLAS_MODEL_ROSTER_START -->"):
            update_readme_roster()
