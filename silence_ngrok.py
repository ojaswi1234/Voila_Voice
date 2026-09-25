import re
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('log.Println("Ngrok started in background")', 'addSysLog("Ngrok", "Ngrok started in background")')
text = text.replace('log.Println("Ngrok authtoken configured successfully")', 'addSysLog("Ngrok", "Ngrok authtoken configured successfully")')
text = text.replace('log.Println("Ngrok is already running")', 'addSysLog("Ngrok", "Ngrok is already running")')

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
