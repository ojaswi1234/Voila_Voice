import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('func main() {')
sys.stdout.buffer.write(text[idx:idx+1500].encode('utf-8'))
