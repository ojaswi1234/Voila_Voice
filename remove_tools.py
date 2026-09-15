import re
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(r'\{\s*Type:\s*\"function\",\s*Function:\s*toolFuncDef\{\s*Name:\s*\"create_pdf\"[\s\S]*?\},\s*\},', '', text)
text = re.sub(r'\{\s*Type:\s*\"function\",\s*Function:\s*toolFuncDef\{\s*Name:\s*\"create_doc\"[\s\S]*?\},\s*\},', '', text)
text = re.sub(r'\{\s*Type:\s*\"function\",\s*Function:\s*toolFuncDef\{\s*Name:\s*\"create_ppt\"[\s\S]*?\},\s*\},', '', text)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
