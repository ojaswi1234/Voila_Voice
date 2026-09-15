import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
open_braces = 0

for line in lines:
    if 'Name:        "docs.' in line:
        # We need to backtrack and remove the '{' and 'Type: "function"' that preceded this
        # Usually it looks like:
        # 	{
        # 		Type: "function",
        # 		Function: toolFuncDef{
        # 			Name:        "docs.templates.list",
        # So we pop the last 3 lines
        popped = 0
        while popped < 3 and len(new_lines) > 0:
            if 'Type: "function"' in new_lines[-1] or 'Function: toolFuncDef{' in new_lines[-1] or new_lines[-1].strip() == '{':
                new_lines.pop()
                popped += 1
            else:
                break
        
        skip = True
        open_braces = 2 # Function block and the outer tool block
        continue
    
    if skip:
        open_braces += line.count('{')
        open_braces -= line.count('}')
        if open_braces <= 0:
            skip = False
        continue
        
    new_lines.append(line)

text = "".join(new_lines)

mcp_prompt = """## Document Generation Rules (Template-First)
- DO NOT invent document structures or coordinates using python scripts.
- Use `docs.templates.list` to find a suitable template.
- Use `docs.templates.get` to see what placeholders it requires.
- Use `docs.create_from_template` to generate the file.
- If a user asks to view recently created documents, use `docs.list_recent` and optionally `docs.open_local`."""

if mcp_prompt in text:
    text = text.replace(mcp_prompt, "")
else:
    import re
    text = re.sub(r'## Document Generation Rules \(Template-First\)[\s\S]*?docs\.open_local`\.', '', text)

# Remove the case for docs in executeToolInner
# case "docs.templates.list", "docs.templates.get", "docs.create_from_template", "docs.list_recent", "docs.open_local":
# 	return callPythonDocumentTool(toolName, argsJSON)
# (Actually I can just regex this one safely)
text = re.sub(r'case \"docs\.templates\.list\"[\s\S]*?callPythonDocumentTool\(toolName, argsJSON\)', '', text)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)

print("Safely removed docs tools.")
