import sys
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

flag_code = """	for _, arg := range os.Args {
		if arg == "--background" || arg == "-b" {
			isBackground = true
		}
	}"""

new_flag_code = """	for _, arg := range os.Args {
		if arg == "--background" || arg == "-b" {
			isBackground = true
		}
		if arg == "--tui" {
			runGraphifyTUI()
			return
		}
	}"""

text = text.replace(flag_code, new_flag_code)
with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
print('Added --tui flag!')
