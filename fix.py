import re

content = open('main.go', 'r', encoding='utf-8').read()

# Add to registerDevice
content = re.sub(r'(log\.Printf\(\"Device registered.*?\n)', r'\1\tgo b.broadcastDevices()\n', content)

# Add to setActiveDevice
content = re.sub(r'(log\.Printf\(\"Active device switched to.*?\n\s+return nil)', r'\tgo b.broadcastDevices()\n\1', content)

# Add to clearAllDevices
content = re.sub(r'(log\.Printf\(\"Cleared all devices.*?\n)', r'\1\tgo b.broadcastDevices()\n', content)

open('main.go', 'w', encoding='utf-8').write(content)
