import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('log.Printf("Using ngrok at: %s", ngrokPath)', '// silenced to prevent tui break')
text = text.replace('log.Println("Starting new ngrok instance...")', '// silenced')
text = text.replace('log.Printf("Failed to start ngrok (attempt %d/%d): %v", ngrokRetryCount, maxNgrokRetries, err)', '// silenced')
text = text.replace('log.Println("Ngrok not running, attempting to start...")', '// silenced')

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
