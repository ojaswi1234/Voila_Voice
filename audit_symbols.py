import sys

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

# Print all lines that contain non-ASCII characters with their line numbers
print("Lines with non-ASCII / emoji characters:")
for i, line in enumerate(lines, 1):
    has_special = any(ord(c) > 127 for c in line)
    if has_special:
        # Show printable + hex for the special chars
        chars = [(c, hex(ord(c))) for c in line if ord(c) > 127]
        print(f"  Line {i}: {line.rstrip()[:120]}")
        print(f"    Chars: {chars[:6]}")
