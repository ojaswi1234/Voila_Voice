with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('var availableTools =')
if idx == -1:
    idx = text.find('var tools =')

if idx != -1:
    print(text[idx:idx+4000])
else:
    print("Tools array not found")
