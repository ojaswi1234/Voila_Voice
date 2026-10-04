import json
import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

names = set(re.findall(r'"name":\s*"([^"]+)"', content))
print("Tools:", ", ".join(names))
