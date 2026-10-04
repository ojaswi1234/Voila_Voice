import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

names = set(re.findall(r'Name:\s*"([^"]+)"', content))
print("Tools:", ", ".join(names))
