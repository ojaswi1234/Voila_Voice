import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

old_call = """				cmdMu.Lock()
				currentCancel = cancel
				cmdMu.Unlock()
				
				output, err := executeGraphifyDAG(ctx, command)"""

new_call = """				cmdMu.Lock()
				currentCancel = cancel
				cmdMu.Unlock()
				
				// Spawn TUI
				exe, _ := os.Executable()
				tuiCmd := exec.Command("cmd.exe", "/c", "start", "Voila Graphify Tracker", exe, "--tui")
				tuiCmd.Start()
				
				output, err := executeGraphifyDAG(ctx, command)"""

text = text.replace(old_call, new_call)
with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
print('Added TUI spawn!')
