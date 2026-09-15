import sys
with open('local-agent/dag_executor.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.lower().find('groq')
sys.stdout.buffer.write(text[idx-200:idx+600].encode('utf-8'))
