import sys
with open('local-agent/dag_executor.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('fatalErr = ')
for i in range(2):
    if idx == -1: break
    print(f"FOUND {i}: {text[idx-50:idx+250]}")
    idx = text.find('fatalErr = ', idx+1)
