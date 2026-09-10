import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# Add focus unfocus to bottom sheets
content = re.sub(r'(void _show[A-Za-z0-9_]+\(BuildContext context\) {\n)', r'\1    FocusScope.of(context).unfocus();\n', content)
# For ones without BuildContext in args but using it
content = re.sub(r'(void _showSecurityAlerts\(\) {\n)', r'\1    FocusScope.of(context).unfocus();\n', content)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print('UI UX Patched')
