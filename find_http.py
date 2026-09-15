import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('req, err := http.NewRequestWithContext(ctx, "POST", apiURL, bytes.NewBuffer(jsonData))')
sys.stdout.buffer.write(text[idx-200:idx+800].encode('utf-8'))
