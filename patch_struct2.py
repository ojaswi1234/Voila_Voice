import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r'URL\s+string\s+json:"url"', 'URL string json:"url"', content)
content = re.sub(r'Width\s+int\s+json:"width"', 'Width int json:"width"', content)
content = re.sub(r'Height\s+int\s+json:"height"', 'Height int json:"height"', content)
content = re.sub(r'\}\s+json:"results"', '} json:"results"', content)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(content)
