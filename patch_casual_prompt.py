import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    code = f.read()

old_prompt = 'prompt := command + "\\n\\n(CRITICAL SYSTEM NOTE:'
new_prompt = 'prompt := command + "\\n\\n(CRITICAL SYSTEM NOTE: Keep your responses casual, brief, and conversational as if you are a friendly voice assistant. Do not use overly formal language.\\n\\nCRITICAL SYSTEM NOTE:'

code = code.replace(old_prompt, new_prompt)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched local-agent/main.go prompt.")
