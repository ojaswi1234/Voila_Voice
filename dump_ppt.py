with open('local-agent/document_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()
start = text.find("def create_ppt")
end = text.find("def create_docx")
print(text[start:end])
