import re

with open('local-agent/document_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_dyn = '''    def generate_dynamic_style(slides_data, theme_hint):
        \"\"\"Generate unique visual style based on task analysis (Option C hybrid approach).\"\"\"'''
new_dyn = '''    def generate_dynamic_style(slides_data, theme_hint):
        \"\"\"Randomized variation, not AI-generated design. (Interim feature)\"\"\"'''

if old_dyn in content:
    content = content.replace(old_dyn, new_dyn)
    with open('local-agent/document_tools.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('document_tools.py dynamic style docstring patched')
else:
    print('Could not find old_dyn in document_tools.py')
