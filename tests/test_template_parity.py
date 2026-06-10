import os
import tempfile
from scripts.check_template_parity import check_parity

def test_template_parity_pass():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        with open(os.path.join(d1, "test.txt"), "w") as f: f.write("hello")
        with open(os.path.join(d2, "test.txt"), "w") as f: f.write("hello")
        
        ok, errors = check_parity(d1, d2)
        assert ok
        assert not errors

def test_template_parity_drift_content():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        with open(os.path.join(d1, "test.txt"), "w") as f: f.write("hello")
        with open(os.path.join(d2, "test.txt"), "w") as f: f.write("world")
        
        ok, errors = check_parity(d1, d2)
        assert not ok
        assert any("content drift" in e for e in errors)

def test_template_parity_missing_file():
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        with open(os.path.join(d1, "test.txt"), "w") as f: f.write("hello")
        
        ok, errors = check_parity(d1, d2)
        assert not ok
        assert any("Files missing in second tree" in e for e in errors)
