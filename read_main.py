with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

start_marker = "4. AUTONOMOUS RESEARCH & CONTENT EXPANSION (FOR NON-TECH USERS):"
idx = text.find(start_marker)
print(text[idx-500:idx+500])
