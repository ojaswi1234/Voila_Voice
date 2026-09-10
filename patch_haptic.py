import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''  void _addMessage(Map<String, dynamic> msg) {
    if (_currentMode.toUpperCase() == 'AGENT') {'''

new_code = '''  void _addMessage(Map<String, dynamic> msg) {
    if (msg['type'] == 'error') {
      HapticFeedback.heavyImpact();
    }
    if (_currentMode.toUpperCase() == 'AGENT') {'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Haptic patched')
else:
    print('Could not find old_code')
