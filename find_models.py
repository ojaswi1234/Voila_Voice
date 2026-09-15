with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    lines = f.readlines()

results = []
for i, line in enumerate(lines):
    ll = line.lower()
    if any(k in ll for k in ['gpt-oss', 'qwen', 'gemma', 'llama', 'mistral', 'groq_model', 'ollama_model',
                               'moonshotai', 'devstral', 'model_list', 'modellist', 'groqmodels', 'ollamamodels',
                               "'model'", '"model"', 'selectedmodel', 'groq', 'ollama']):
        results.append(f"{i+1}: {line.rstrip()}")

for r in results[:80]:
    print(r)
