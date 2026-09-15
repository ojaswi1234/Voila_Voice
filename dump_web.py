import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('case "web_research":')
idx2 = text.find('case "read_file":', idx)
print(text[idx:idx2])
