import sys

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

results = []
for i, line in enumerate(lines, 1):
    has_special = any(ord(c) > 127 for c in line)
    if has_special:
        chars = [(hex(ord(c)), c) for c in line if ord(c) > 127]
        results.append(f"Line {i}: chars={chars[:8]}")

with open('symbol_audit.txt', 'w', encoding='utf-8') as out:
    out.write('\n'.join(results))

print("Done. Results in symbol_audit.txt")
