import re

with open('main.go', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('func (b *Backend) generateMockResponse(command string) string {', 'func (b *Backend) _deprecated_generateMockResponse(command string) string {')

content = re.sub(r'mockResp := b\.generateMockResponse\(cmd\)', 'mockResp := decoy.GenerateMockResponse(cmd)', content)
if 'voice-cli-system/shared/decoy' not in content:
    content = content.replace('import (', 'import (\n\t"voice-cli-system/shared/decoy"\n')

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(content)
