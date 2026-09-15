with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

import re

# find create_excel
idx1 = text.find('Name:        "create_excel"')
if idx1 != -1:
    end_idx = text.find('}', text.find('"required":', idx1))
    old_req = text[text.find('"required":', idx1):end_idx]
    if '"design_strategy"' not in old_req:
        new_req = old_req.replace(']', ', "design_strategy"]')
        text = text[:text.find('"required":', idx1)] + new_req + text[end_idx:]

# find create_csv
idx2 = text.find('Name:        "create_csv"')
if idx2 != -1:
    end_idx = text.find('}', text.find('"required":', idx2))
    old_req = text[text.find('"required":', idx2):end_idx]
    if '"design_strategy"' not in old_req:
        new_req = old_req.replace(']', ', "design_strategy"]')
        text = text[:text.find('"required":', idx2)] + new_req + text[end_idx:]

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
