with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8-sig') as f:
    text = f.read()

# Remove orphaned control bytes (the last remnants of broken encoding)
text = text.replace('\x81', '').replace('\x8f', '').replace('\x9d', '').replace('\x9c', '').replace('\x8d', '')

# Also fix the GROQ icon specifically to be clean
text = text.replace(' GROQ"', '⚡ GROQ"')

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8-sig', newline='\r\n') as f:
    f.write(text)

print("Cleaned control bytes")

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8-sig') as f:
    lines = f.readlines()

print("L167:", lines[166][:80].strip())
print("L172:", lines[171][:100].strip())
