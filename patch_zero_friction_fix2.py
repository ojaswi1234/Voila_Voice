import re

with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('"crypto/hmac"', '"crypto/hmac"\n\t"crypto/rand"')

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
