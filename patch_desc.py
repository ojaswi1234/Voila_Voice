import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# Update tool description
content = content.replace(
    '\"description\": \"Search type: \'text\' (default, DuckDuckGo text search) or \'image\' (Picsum random image search)\"',
    '\"description\": \"Search type: \'text\' (default, DuckDuckGo text search) or \'image\' (Openverse CC image search)\"'
)

content = content.replace(
    '\"description\": \"If true, AI will automatically search for and download relevant images for content/image slides using web_research\"',
    '\"description\": \"If true, AI will automatically search for and download relevant images using Openverse API for content/image slides\"'
)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(content)
