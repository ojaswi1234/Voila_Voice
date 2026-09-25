import re

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Hide desktop cursor
new_desktop = '''            elif visual_state == "DESKTOP":
                  target_text = "Desktop"
                  target_color = '#a78bfa'
                  target_outline = '#7c3aed'
                  show_dots = True
                  canvas.itemconfig(sun_glow3, state="hidden")
                  canvas.itemconfig(browser_box, state="hidden")
                  canvas.itemconfig(browser_line, state="hidden")
                  canvas.itemconfig(desktop_cursor_arrow, state="hidden")
                  canvas.itemconfig(desktop_cursor_dot, state="hidden")
                  canvas.itemconfig(desktop_cursor_label, state="hidden")'''
text = re.sub(r'            elif visual_state == "DESKTOP":.*?canvas\.itemconfig\(desktop_cursor_label, state="normal"\)', new_desktop, text, flags=re.DOTALL)

# 2. Add Black Hole & send_cursor_home
new_logic = '''def trigger_black_hole():
    hole_id = canvas.create_oval(cx, cy, cx, cy, fill="black", outline="#a78bfa", width=2)
    def animate_hole(frame=0):
        if frame < 20:
            r = frame * 2
            canvas.coords(hole_id, cx-r, cy-r, cx+r, cy+r)
            root.after(20, animate_hole, frame+1)
        elif frame < 40:
            root.after(20, animate_hole, frame+1)
        elif frame < 60:
            r = (60 - frame) * 2
            canvas.coords(hole_id, cx-r, cy-r, cx+r, cy+r)
            root.after(20, animate_hole, frame+1)
        else:
            canvas.delete(hole_id)
    animate_hole()

def send_cursor_home():
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        x = root.winfo_x() + 40
        y = root.winfo_y() + 32
        sock.sendto(f"HOME,{x},{y}".encode(), ("127.0.0.1", 19882))
        trigger_black_hole()
    except Exception:
        pass'''

text = text.replace('''def reset_to_idle():
    global ai_state
    if ai_state != "IDLE":
        ai_state = "IDLE"
        update_expression()''', '''def reset_to_idle():
    global ai_state
    if ai_state != "IDLE":
        ai_state = "IDLE"
        update_expression()

''' + new_logic)

# Trigger send_cursor_home on IDLE
new_idle = '''    if "STATUS: IDLE" in line:
        if glow_timer: root.after_cancel(glow_timer)
        send_cursor_home()
        glow_timer = root.after(1500, reset_to_idle)
        return

    if "STATUS: FORCE_IDLE" in line:
        if glow_timer: root.after_cancel(glow_timer)
        send_cursor_home()
        reset_to_idle()
        return'''
text = re.sub(r'    if "STATUS: IDLE" in line:.*?return', new_idle, text, flags=re.DOTALL, count=2)

# 3. Add Cache File Writing safely
new_path_def = '''import math\nimport os\n_popup_pos_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "popup_pos.txt")'''
text = text.replace('import math', new_path_def, 1)

new_stop_move = '''def stop_move(e):
    if dashboard_active or dashboard_transition_in_progress:
        return
    root.x, root.y = None, None
    try:
        with open(_popup_pos_path, "w") as f:
            f.write(f"{root.winfo_x()},{root.winfo_y()}")
    except:
        pass'''
text = re.sub(r'def stop_move\(e\):.*?root\.x, root\.y = None, None', new_stop_move, text, flags=re.DOTALL)

end_startup = '''def write_initial_pos():
    try:
        with open(_popup_pos_path, "w") as f:
            f.write(f"{root.winfo_x()},{root.winfo_y()}")
    except:
        pass
    root.after(5000, write_initial_pos)

export_graphify_prompt()
root.after(100, write_initial_pos)
root.mainloop()'''
text = text.replace('export_graphify_prompt()\n\nroot.mainloop()', end_startup)

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(text)
print("Safely repatched")
