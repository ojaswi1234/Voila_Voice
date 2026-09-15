import sys
with open('main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('if mode == "" {')
sys.stdout.buffer.write(text[idx-300:idx+300].encode('utf-8'))
