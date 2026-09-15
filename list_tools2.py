import sys
import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('var availableTools')
idx2 = text.find('func executeToolInner(')

block = text[idx:idx2]
names = re.findall(r'Name:\s*"(.*?)"', block)
print("Tools in availableTools:", names)
