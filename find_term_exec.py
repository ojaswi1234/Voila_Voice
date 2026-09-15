import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('voila_ipc_server.ps1')
sys.stdout.buffer.write(text[idx+1000:idx+2500].encode('utf-8'))
