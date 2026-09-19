with open("local-agent/run_hidden_agent_backup.pyw", "r", encoding="utf-8") as f:
    text = f.read()

with open("local-agent/run_hidden_agent.pyw", "w", encoding="utf-8") as f:
    f.write(text)
