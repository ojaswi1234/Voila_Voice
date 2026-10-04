import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# find /execute block
match = re.search(r'mux\.HandleFunc\("/execute", func.*?var req map\[string\]interface\{\}(.*?)\}\)', content, re.DOTALL)
if match:
    print(match.group(1)[:2000])
else:
    print("Not found")
