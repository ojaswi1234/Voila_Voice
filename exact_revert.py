import re
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

# exact block removal for list
block = """	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.templates.list",
			Description: "List available document templates from the registry.",
			Parameters: map[string]interface{}{"type": "object", "properties": map[string]interface{}{}},
		},
	},"""
text = text.replace(block, "")

# exact block removal for get
block = """	{
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
	},"""
text = text.replace(block, "")

# exact block removal for create
block = """	{
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
	},"""
text = text.replace(block, "")

# exact block removal for list_recent
block = """	{
		Type: "function",
		Function: toolFuncDef{
			Name:        "docs.list_recent",
			Description: "List recently generated documents.",
			Parameters: map[string]interface{}{"type": "object", "properties": map[string]interface{}{}},
		},
	},"""
text = text.replace(block, "")

# exact block removal for open_local
block = """	{
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
	},"""
text = text.replace(block, "")

# System Prompt
text = re.sub(r'## Document Generation Rules \(Template-First\)[\s\S]*?docs\.open_local`\.', '', text)

# executeToolInner case
text = re.sub(r'case \"docs\.templates\.list\"[\s\S]*?callPythonDocumentTool\(toolName, argsJSON\)', '', text)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)

print("Exact replace done.")
