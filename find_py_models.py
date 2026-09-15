import sys

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

results = []
for i, line in enumerate(lines):
    ll = line.lower()
    if any(k in ll for k in ['gpt-oss', 'qwen', 'gemma', 'llama', 'mistral', 'groq_model', 'ollama_model',
                               'moonshotai', 'devstral', 'groqmodels', 'ollamamodels', 'compound',
                               'selectedmodel', 'llm_model', 'model_name', 'model_list',
                               'optionmenu', 'ttk.combobox', 'combobox', 'available_model']):
        results.append(f"{i+1}: {line.rstrip()}")

sys.stdout.buffer.write('\n'.join(results).encode('utf-8'))
