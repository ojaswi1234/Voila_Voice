with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
lines = text.split('\n')
for i, line in enumerate(lines):
    if 'case "create_pdf":' in line or 'case "create_doc":' in line or 'case "create_ppt":' in line:
        print(f'Line {i}: {line.strip()}')
