import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('/api/chat')
if idx != -1:
    sys.stdout.buffer.write(text[idx-200:idx+800].encode('utf-8'))
