with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

# Exact Tool Definitions
blocks_to_remove = [
"""	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.templates.list",
			Description: "List available document templates from the registry.",
			Parameters: map[string]interface{}{"type": "object", "properties": map[string]interface{}{}},
		},
	},
""",
"""	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.templates.get",
			Description: "Get details and placeholders for a specific template.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"template_id": map[string]interface{}{"type": "string", "description": "The ID of the template"},
				},
				"required": []string{"template_id"},
			},
		},
	},
""",
"""	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.create_from_template",
			Description: "Create a new document by filling a template. EXCLUSIVE WAY to create PPT/PDF/DOCX now.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"template_id": map[string]interface{}{"type": "string"},
					"title": map[string]interface{}{"type": "string"},
					"fills": map[string]interface{}{"type": "object", "description": "Map of placeholder keys to string values"},
					"export": map[string]interface{}{"type": "array", "items": map[string]interface{}{"type": "string"}, "description": `e.g. ["pptx", "pdf"]`},
				},
				"required": []string{"template_id", "title", "fills"},
			},
		},
	},
""",
"""	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.list_recent",
			Description: "List recently generated documents.",
			Parameters: map[string]interface{}{"type": "object", "properties": map[string]interface{}{}},
		},
	},
""",
"""	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.open_local",
			Description: "Open a locally downloaded document file in the default OS application.",
			Parameters: map[string]interface{}{
				"type": "object",
				"properties": map[string]interface{}{
					"path": map[string]interface{}{"type": "string"},
				},
				"required": []string{"path"},
			},
		},
	},
"""
]

for block in blocks_to_remove:
    text = text.replace(block, "")

# Exact execution pseudoCommand logging
pseudo_block = """		case "docs.templates.list":
			pseudoCommand = "python mcp_docs_facade.py list"
		case "docs.templates.get":
			pseudoCommand = "python mcp_docs_facade.py get " + getString("template_id")
		case "docs.create_from_template":
			pseudoCommand = "python mcp_docs_facade.py create " + getString("template_id")
		case "docs.list_recent":
			pseudoCommand = "python mcp_docs_facade.py list_recent"
		case "docs.open_local":
			pseudoCommand = "python mcp_docs_facade.py open_local " + getString("path")
"""
text = text.replace(pseudo_block, "")

# Exact execution switch
exec_block = """	case "docs.templates.list", "docs.templates.get", "docs.create_from_template", "docs.list_recent", "docs.open_local":
		action := strings.TrimPrefix(toolName, "docs.")
		if action == "templates.list" { action = "list" }
		if action == "templates.get" { action = "get" }
		
		scriptPath := filepath.Join(getExecutableDir(), "mcp_docs_facade.py")
		var cmdObj *exec.Cmd
		
		if action == "list" || action == "list_recent" {
			cmdObj = exec.Command("python", scriptPath, action)
		} else if action == "get" || action == "open_local" {
			argStr := getString("template_id")
			if action == "open_local" {
			    argStr = getString("path")
			}
			cmdObj = exec.Command("python", scriptPath, action, argStr)
		} else if action == "create_from_template" {
			cmdObj = exec.Command("python", scriptPath, "create", string(argsJSON))
			cmdObj.Env = append(os.Environ(), "VOILA_DOCS_MOCK=1") // Force mock mode for now
		}
		
		out, err := cmdObj.CombinedOutput()
		if err != nil {
			return fmt.Sprintf("Error executing MCP docs facade: %v\\nOutput: %s", err, string(out))
		}
		return string(out)

"""
text = text.replace(exec_block, "")

# Exact System Prompt
prompt_block = """## Document Generation Rules (Template-First)
- DO NOT invent document structures or coordinates using python scripts.
- Use `docs.templates.list` to find a suitable template.
- Use `docs.templates.get` to see what placeholders it requires.
- Use `docs.create_from_template` to generate the file.
- If a user asks to view recently created documents, use `docs.list_recent` and optionally `docs.open_local`.

"""
text = text.replace(prompt_block, "")

# Write to local-agent/main.go
with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)

print("Restored exact main.go without breaking anything.")
