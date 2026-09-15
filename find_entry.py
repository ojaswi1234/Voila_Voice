import sys
with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('Entry(')
for i in range(5):
    if idx == -1: break
    print(f"FOUND ENTRY {i}: {text[idx-100:idx+300]}")
    idx = text.find('Entry(', idx+1)
