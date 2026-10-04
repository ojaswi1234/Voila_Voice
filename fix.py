import re
with open('local-agent/background_tasks.go', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'Label\s+string\s+json.*?Runtime-only', 'Label string `json:"label"`\n\tConversationID string `json:"conversation_id"`\n\n\t// Runtime-only', content, flags=re.DOTALL)

with open('local-agent/background_tasks.go', 'w', encoding='utf-8') as f:
    f.write(content)
