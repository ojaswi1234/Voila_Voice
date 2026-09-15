import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('currentCancel      context.CancelFunc', 'currentCancel      context.CancelFunc\n\tisGraphifyRunning bool')

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
print('Defined isGraphifyRunning!')
