import re
with open(r"local-agent\main.go", "r", encoding="utf-8") as f:
    content = f.read()

bad_string = r'Additionally, if you use terminal tools and then transition to desktop tools, you should use the desktop_automation tool to physically click the "Minimize" button of your terminal window using the custom cursor so it does not obstruct the desktop. '

content = content.replace(bad_string, "")

with open(r"local-agent\main.go", "w", encoding="utf-8") as f:
    f.write(content)
print("Removed aggressive minimize instruction from prompt.")
