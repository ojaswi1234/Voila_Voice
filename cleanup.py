content = open('local-agent/document_tools.py', encoding='utf-8').read()

content = content.replace(
    'fd, temp_html = tempfile.mkstemp(suffix=".html")\n            print(f"HTML AT: {temp_html}")\n            import shutil\n            shutil.copy(temp_html, "debug_html.html")',
    'fd, temp_html = tempfile.mkstemp(suffix=".html")'
)
content = content.replace(
    "        import shutil\n        shutil.copy(temp_html_path, 'debug_html.html')\n",
    ''
)
# Also restore os.unlink
content = content.replace('        # os.unlink(temp_html_path)', '        os.unlink(temp_html_path)')

open('local-agent/document_tools.py', 'w', encoding='utf-8').write(content)
print('Cleaned up debug patches')
