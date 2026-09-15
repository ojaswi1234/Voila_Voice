import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

old_block = """	for _, arg := range os.Args {
		if arg == "--background" || arg == "-b" {
			backgroundMode = true
			break
		}
	}"""

new_block = """	for _, arg := range os.Args {
		if arg == "--background" || arg == "-b" {
			backgroundMode = true
		}
		if arg == "--tui" {
			runGraphifyTUI()
			return
		}
	}"""

text = text.replace(old_block, new_block)
with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
print("Re-added --tui flag!")
