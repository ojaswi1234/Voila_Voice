import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('mux.HandleFunc')
sys.stdout.buffer.write(text[idx:idx+800].encode('utf-8'))
