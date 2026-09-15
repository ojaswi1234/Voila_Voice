import re

with open('main_backup.go', 'r', encoding='utf-8') as f:
    text = f.read()

# We need to remove the docs.* tools
def remove_tool(name):
    global text
    pattern = r'\{\s*Type:\s*\"function\",\s*Function:\s*toolFuncDef\{\s*Name:\s*\"' + name.replace('.', r'\.') + r'\"[\s\S]*?\},\s*\},'
    text = re.sub(pattern, '', text)

remove_tool('docs.templates.list')
remove_tool('docs.templates.get')
remove_tool('docs.create_from_template')
remove_tool('docs.list_recent')
remove_tool('docs.open_local')

# Now let's remove MCP template instructions from the system prompt
mcp_prompt = """## Document Generation Rules (Template-First)
- DO NOT invent document structures or coordinates using python scripts.
- Use `docs.templates.list` to find a suitable template.
- Use `docs.templates.get` to see what placeholders it requires.
- Use `docs.create_from_template` to generate the file.
- If a user asks to view recently created documents, use `docs.list_recent` and optionally `docs.open_local`."""

if mcp_prompt in text:
    text = text.replace(mcp_prompt, "")
else:
    # try regex
    text = re.sub(r'## Document Generation Rules \(Template-First\)[\s\S]*?docs\.open_local`\.', '', text)

# Remove MCP logic from executeToolInner
# Find the case statement for docs.*
mcp_case = r'case \"docs\.templates\.list\", \"docs\.templates\.get\", \"docs\.create_from_template\", \"docs\.list_recent\", \"docs\.open_local\":[\s\S]*?return result'
text = re.sub(mcp_case, '', text)

# Write to local-agent/main.go
with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)

print("Restored main.go tools!")
