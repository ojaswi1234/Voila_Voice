with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

for tool in ['create_doc', 'create_excel', 'create_csv']:
    idx = text.find(f'Name:        "{tool}"')
    print(text[idx:idx+800])
