import sys
with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('+ Add Node')
sys.stdout.buffer.write(text[idx-100:idx+300].encode('utf-8'))
