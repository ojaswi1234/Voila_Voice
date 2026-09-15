with open('main.go', 'r', encoding='utf-8') as f:
    text = f.read()

for i, line in enumerate(text.split('\n')):
    if '"command"' in line:
        print(f'{i}: {line}')
