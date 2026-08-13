import re

with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# Add crypto/rand properly
if '"crypto/rand"' not in content:
    content = content.replace('"crypto/subtle"', '"crypto/rand"\n\t"crypto/subtle"')

# Add var sessionSigningKey []byte below imports
if 'var sessionSigningKey []byte' not in content:
    content = content.replace(')', ')\n\nvar sessionSigningKey []byte', 1)

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
