with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("('Documents', 'Documents'),", "")

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(text)
