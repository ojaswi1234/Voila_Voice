import re
with open('local-agent/desktop_core.py', 'r', encoding='utf-8') as f:
    text = f.read()

old_walk = '''        b = meta["bounds"]
        if b["w"] > 0 or b["h"] > 0 or meta["name"]:'''

new_walk = '''        b = meta["bounds"]
        is_container = meta["role"] in ("PaneControl", "GroupControl", "WindowControl", "CustomControl")
        has_content = bool(meta["name"] or meta["value"] or meta["automation_id"])
        is_useful = not is_container or has_content
        
        if (b["w"] > 0 or b["h"] > 0 or meta["name"]) and is_useful:'''

if old_walk in text:
    text = text.replace(old_walk, new_walk)
else:
    print("Could not find old_walk block")

with open('local-agent/desktop_core.py', 'w', encoding='utf-8') as f:
    f.write(text)
