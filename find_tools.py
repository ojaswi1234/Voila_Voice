import sys
import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('func executeToolInner(')
idx2 = text.find('// ── Groq executor with tool-calling loop', idx)
block = text[idx:idx2]

implemented = set()
for line in block.split('\n'):
    if 'case ' in line and '"' in line:
        matches = re.findall(r'"([^"]+)"', line)
        for m in matches:
            if m:
                implemented.add(m)

print("Implemented inside executeToolInner:")
print(sorted(list(implemented)))
