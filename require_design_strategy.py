with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    '"required": []string{"path", "content", "theme"},',
    '"required": []string{"path", "content", "theme", "design_strategy"},'
)

text = text.replace(
    '"required": []string{"path", "title", "theme", "slides"},',
    '"required": []string{"path", "title", "theme", "design_strategy", "slides"},'
)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
