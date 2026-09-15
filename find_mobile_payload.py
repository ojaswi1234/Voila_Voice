import sys
with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('payload = {')
sys.stdout.buffer.write(text[idx-500:idx+800].encode('utf-8'))
