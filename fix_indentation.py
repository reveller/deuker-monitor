#!/usr/bin/env python3
"""Fix the _check_extra_documents_tab function indentation"""

# Read the entire file
with open('deuker-monitor.py.backup', 'r') as f:
    lines = f.readlines()

# Find the function start and end
func_start = None
func_end = None
for i, line in enumerate(lines):
    if 'def _check_extra_documents_tab' in line:
        func_start = i
    elif func_start is not None and line.strip().startswith('def ') and '_check_extra_documents_tab' not in line:
        func_end = i
        break

if func_start is None:
    print("Could not find function start")
    exit(1)

print(f"Function spans lines {func_start+1} to {func_end}")

# Write everything before the function
with open('deuker-monitor.py', 'w') as f:
    f.writelines(lines[:func_start])

print(f"Wrote {func_start} lines before function")
print("Function will be replaced - keeping file truncated for manual fix")
