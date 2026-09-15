import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('browser_automation')
if idx != -1:
    print(text[idx-200:idx+400])
else:
    print("Not found")
