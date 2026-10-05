import sys

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

def extract_method(method_name):
    start = -1
    for i, line in enumerate(lines):
        if f'Widget {method_name}' in line:
            start = i
            break
    if start == -1: return 'Not found'
    stack = []
    end = start
    for i in range(start, len(lines)):
        for char in lines[i]:
            if char == '{': stack.append('{')
            elif char == '}': 
                if stack: stack.pop()
        if len(stack) == 0 and i > start:
            end = i
            break
    return '\n'.join(lines[start:end+1])

print('=== _buildDrawer ===')
print(extract_method('_buildDrawer'))
print('=== _buildSubtitleOverlay ===')
print(extract_method('_buildSubtitleOverlay'))
print('=== _buildJobStrip ===')
print(extract_method('_buildJobStrip'))
