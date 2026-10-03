import re
with open("mobile-agent/lib/main.dart", "r", encoding="utf-8") as f:
    content = f.read()

# find blocks with 'await' then 'setState' without 'mounted' in between
matches = re.finditer(r'await\s+[^;]+;[^}]+setState', content, re.DOTALL)
for m in matches:
    text = m.group(0)
    if 'mounted' not in text:
        print("FOUND POTENTIAL UNMOUNTED SETSTATE:\n", text[:100], "\n...")
