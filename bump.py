import re
from pathlib import Path

files_to_update = list(Path('.').rglob('*.py')) + list(Path('.').rglob('*.md')) + list(Path('.').rglob('*.json'))

for f in files_to_update:
    if not f.is_file(): continue
    if 'node_modules' in str(f) or '.git' in str(f): continue
    
    try:
        text = f.read_text('utf-8')
    except Exception:
        continue
        
    orig_text = text
    
    # 0.5.9 -> 0.5.9
    text = text.replace('0.5.9', '0.5.9')
    
    # Update scripts that refer to PUBLIC_TAG
    if 'scripts/' in str(f) and f.suffix == '.py':
        text = text.replace('PUBLIC_TAG = "v0.5.8.1"', 'PUBLIC_TAG = "v0.5.9"')
        text = text.replace('PUBLIC_TAG = "0.5.8.1"', 'PUBLIC_TAG = "0.5.9"')
        text = text.replace('ACTIVE_RELEASE_TAG = "v0.5.8.1"', 'ACTIVE_RELEASE_TAG = "v0.5.9"')
        text = text.replace('EXPECTED_VERSION = "0.5.8.1"', 'EXPECTED_VERSION = "0.5.9"')
        # check_v0581_hotfix_cutover -> we probably shouldn't break its historical logic
        # wait, if I replace EXPECTED_VERSION = "0.5.9" in check_v0581_hotfix_cutover.py, its error messages will change, and its tests will fail.

    if f.name == 'README.md':
        text = text.replace('v0.5.8.1', 'v0.5.9')
        text = text.replace('0.5.8.1', '0.5.9')
    
    if text != orig_text:
        f.write_text(text, 'utf-8')
        print(f"Updated {f}")

