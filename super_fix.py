import re
with open('local-agent/desktop_core.py', 'r', encoding='utf-8') as f:
    text = f.read()

# I will find all variations of this broken logic and replace them.
# The broken logic looks like:
#             meta = _ctrl_meta(ctrl)
#             if meta.get("clickable_point"):
#             cx, cy = meta["clickable_point"]
#         else:
#             cx, cy = _center(meta["bounds"])

def fix_broken_blocks(text):
    # act_invoke, act_scroll, act_set_value, act_type_keys, _move_to_ref
    
    # We want to replace ANY block that tries to get clickable_point from meta.
    # Since I broke the indentation, I will use a regex that catches varying whitespace.
    
    pattern = r'(\s*)meta = _ctrl_meta\(ctrl\)\s*(?:if meta\.get\("clickable_point"\):\s*cx, cy = meta\["clickable_point"\]\s*else:\s*|cx, cy = None, None\s*try:\s*pt = ctrl\.GetClickablePoint\(\)\s*if pt:\s*cx, cy = int\(pt\[0\]\), int\(pt\[1\]\)\s*except Exception:\s*pass\s*if cx is None:\s*)cx, cy = _center\(meta\["bounds"\]\)'
    
    def repl(m):
        indent = m.group(1)
        return (indent + 'meta = _ctrl_meta(ctrl)\n' +
                indent + 'cx, cy = None, None\n' +
                indent + 'try:\n' +
                indent + '    pt = ctrl.GetClickablePoint()\n' +
                indent + '    if pt: cx, cy = int(pt[0]), int(pt[1])\n' +
                indent + 'except Exception: pass\n' +
                indent + 'if cx is None: cx, cy = _center(meta["bounds"])')
                
    text = re.sub(pattern, repl, text)
    
    # Also fix _move_to_ref which might have different indentation
    pattern2 = r'(\s*)meta = _ctrl_meta\(ctrl\)\n\s*if meta\.get\("clickable_point"\):\n\s*cx, cy = meta\["clickable_point"\]\n\s*else:\n\s*cx, cy = _center\(meta\["bounds"\]\)'
    text = re.sub(pattern2, repl, text)
    
    return text

text = fix_broken_blocks(text)

with open('local-agent/desktop_core.py', 'w', encoding='utf-8') as f:
    f.write(text)
