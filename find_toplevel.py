import sys
with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('def edit_node')
if idx == -1:
    idx = text.find('def ')

    import re
    m = re.search(r'def .*edit.*', text)
    if m:
        idx = m.start()
    else:
        m = re.search(r'Toplevel\(', text)
        if m:
            idx = m.start()

sys.stdout.buffer.write(text[idx:idx+2500].encode('utf-8'))
