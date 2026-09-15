import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()
idx = text.find('case "run_terminal":')
idx2 = text.find('case "run_terminal":', idx+1)
sys.stdout.buffer.write(text[idx2:idx2+1500].encode('utf-8'))
