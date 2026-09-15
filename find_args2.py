import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('--background')
sys.stdout.buffer.write(text[max(0, idx-1000):idx+500].encode('utf-8'))
