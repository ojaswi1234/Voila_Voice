import re
with open('local-agent/desktop_core.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Remove clickable_point from _ctrl_meta entirely
old_meta = '''
        clickable_point = None
        try:
            pt = ctrl.GetClickablePoint()
            if pt:
                clickable_point = [int(pt[0]), int(pt[1])]
        except Exception:
            pass

        return {
            "clickable_point": clickable_point,
'''
new_meta = '''
        return {
'''
if old_meta.strip('\n') in text:
    text = text.replace(old_meta.strip('\n'), new_meta.strip('\n'))

# 2. Re-write the coordinate extraction logic to do it inline without polluting _ctrl_meta
# We need to replace `meta = _ctrl_meta(ctrl)` and the if block that follows it in all action functions.
# The actions are _move_to_ref, act_scroll, act_set_value, act_type_keys, act_drag_ref.

def replace_inline(text):
    # Find all instances of:
    # meta = _ctrl_meta(ctrl)
    # if meta.get("clickable_point"):
    #     cx, cy = meta["clickable_point"]
    # else:
    #     cx, cy = _center(meta["bounds"])
    
    target = '''        meta = _ctrl_meta(ctrl)
        if meta.get("clickable_point"):
            cx, cy = meta["clickable_point"]
        else:
            cx, cy = _center(meta["bounds"])'''
            
    replacement = '''        # Live update at exact millisecond
        meta = _ctrl_meta(ctrl)
        cx, cy = None, None
        try:
            pt = ctrl.GetClickablePoint()
            if pt:
                cx, cy = int(pt[0]), int(pt[1])
        except Exception:
            pass
        if cx is None:
            cx, cy = _center(meta["bounds"])'''
            
    return text.replace(target, replacement)

text = replace_inline(text)

with open('local-agent/desktop_core.py', 'w', encoding='utf-8') as f:
    f.write(text)
