import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('mux.HandleFunc("/execute"')
idx2 = text.find('mux.HandleFunc("/models"', idx)
with open('dump_out.txt', 'w', encoding='utf-8') as f:
    f.write(text[idx:idx2])
