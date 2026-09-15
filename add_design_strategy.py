with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

# Update create_pdf schema to include design_strategy
pdf_insertion = '''
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your LaTeX generation:
- "McKinsey Consulting Report": Enforces BLUF (Bottom Line Up Front), strict two-column layouts, heavy data tables, and minimal corporate styling.
- "Academic Whitepaper (IEEE/Nature)": Enforces standard LaTeX academic margins, complex tabularx datasets, and highly rigorous technical prose.
- "Creative Apple-Style Pitch": Enforces massive text sizes, extreme minimalism, huge margins, and striking use of negative space.
- "FlowGPT Visual Infographic": Uses dense, highly visual layouts, bullet point grids, and colorful accent blocks.`},'''

# Update create_ppt schema to include design_strategy
ppt_insertion = '''
					"design_strategy": map[string]interface{}{"type": "string", "description": `Select a Global Marketplace Skill Prompt to guide your slide design:
- "PromptBase Y-Combinator Pitch Deck": Forces problem-solution structure, large metric callouts, and minimalist startup aesthetics.
- "McKinsey Strategy Deck": Forces dense data slides, actionable slide titles, 6x6 rule, and highly analytical visual blocks.
- "SnackPrompt Storytelling Flow": Uses quote blocks, full-image backgrounds, and narrative-driven section dividers.`},'''

# Find the properties block for create_pdf
idx_pdf = text.find('"theme":     map[string]interface{}{"type": "string", "description": "Theme name: corporate_blue, cyberpunk, minimalist, modern_dark"},')
if idx_pdf != -1:
    text = text[:idx_pdf] + pdf_insertion.strip() + '\n\t\t\t\t\t' + text[idx_pdf:]

# Find the properties block for create_ppt
idx_ppt = text.find('"theme": map[string]interface{}{"type": "string", "description": `Theme name')
if idx_ppt != -1:
    text = text[:idx_ppt] + ppt_insertion.strip() + '\n\t\t\t\t\t' + text[idx_ppt:]

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
