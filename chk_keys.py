import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('"/api-keys"')
if idx != -1:
    sys.stdout.buffer.write(text[idx-500:idx+1500].encode('utf-8'))
