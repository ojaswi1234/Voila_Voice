import sys
with open('main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('"/webhook/result"')
if idx != -1:
    idx2 = text.rfind('func ', 0, idx)
    sys.stdout.buffer.write(text[idx2:idx+1500].encode('utf-8'))
