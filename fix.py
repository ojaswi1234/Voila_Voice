import re
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace('"Command failed:\n" + err.Error()', '"Command failed:\\n" + err.Error()')

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(code)
