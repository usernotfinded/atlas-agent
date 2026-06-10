#!/usr/bin/env python3
import os
import sys
import filecmp

def check_parity(tree1, tree2):
    if not os.path.exists(tree1) or not os.path.exists(tree2):
        return False, ["Directories not found"]
        
    def get_files(tree_path):
        files = []
        for root, _, filenames in os.walk(tree_path):
            for name in filenames:
                rel_path = os.path.relpath(os.path.join(root, name), tree_path)
                files.append(rel_path)
        return set(files)
        
    files1 = get_files(tree1)
    files2 = get_files(tree2)
    
    errors = []
    
    missing_in_2 = files1 - files2
    if missing_in_2:
        errors.append(f"Files missing in second tree: {missing_in_2}")
        
    missing_in_1 = files2 - files1
    if missing_in_1:
        errors.append(f"Files missing in first tree: {missing_in_1}")
        
    common_files = files1.intersection(files2)
    for f in common_files:
        f1 = os.path.join(tree1, f)
        f2 = os.path.join(tree2, f)
        if not filecmp.cmp(f1, f2, shallow=False):
            errors.append(f"File content drift detected in: {f}")
            
    return len(errors) == 0, errors

def main():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_tree = os.path.join(root_dir, "templates", "routine-trader")
    src_tree = os.path.join(root_dir, "src", "atlas_agent", "templates", "routine-trader")
    
    ok, errors = check_parity(template_tree, src_tree)
    if not ok:
        for err in errors:
            print(err)
        print("Template parity check FAILED.")
        sys.exit(1)
    else:
        print("Template parity check PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
