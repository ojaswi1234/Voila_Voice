import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('--tui')
sys.stdout.buffer.write(text[idx-200:idx+300].encode('utf-8'))
