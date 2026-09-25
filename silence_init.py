import re
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('log.Printf("Network resilience manager initialized with %d transport layers", len(resilienceManager.transportStack.transports))', '// silenced')
text = text.replace('log.Printf("Auto-connecting with backend: %s", data.BackendURL)', 'addSysLog("System", fmt.Sprintf("Auto-connecting with backend: %s", data.BackendURL))')
text = text.replace('log.Println("Local agent server starting on :8088")', 'addSysLog("Server", "Local agent server starting on :8088")')

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
