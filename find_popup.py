import sys
with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('"prompt"')
sys.stdout.buffer.write(text[idx-200:idx+2000].encode('utf-8'))
