import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('mux.HandleFunc("/execute"')
if idx == -1:
    idx = text.find('http.HandleFunc("/execute"')

idx2 = text.find('mux.HandleFunc("/stop"', idx)
if idx2 == -1:
    idx2 = text.find('http.HandleFunc("/stop"', idx)

print(text[idx:idx2])
