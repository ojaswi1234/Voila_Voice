import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('URL string json:"url"', 'URL string `json:"url"`')
content = content.replace('Width int json:"width"', 'Width int `json:"width"`')
content = content.replace('Height int json:"height"', 'Height int `json:"height"`')
content = content.replace('} json:"results"', '} `json:"results"`')

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(content)
