import re
with open('local-agent/document_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace('img_path = os.path.join(cache_dir, f"{cache_key}.svg")', 'img_path = os.path.join(cache_dir, f"{cache_key}.png")')
with open('local-agent/document_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)
