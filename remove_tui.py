import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the TUI launching block
start_str = "// Force spawn a completely independent Windows Terminal or PowerShell window"
end_str = "if !isTUIMode { os.Stdout.Sync() }"

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + 'fmt.Println("STATUS: GRAPHIFY")\n\t\t\tos.Stdout.Sync()\n\n\t\t\t' + content[end_idx + len(end_str):]
    with open('local-agent/main.go', 'w', encoding='utf-8') as f:
        f.write(content)
    print("TUI launching removed.")
else:
    print("Could not find TUI block.")
