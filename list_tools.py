import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(r'Name:\s*"([^"]+)"', text)
print("Tools found:", list(set(matches)))
