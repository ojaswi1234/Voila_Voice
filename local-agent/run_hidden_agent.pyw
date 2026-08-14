import tkinter as tk
import subprocess
import threading
import sys
import time

CREATE_NO_WINDOW = 0x08000000
subprocess.run(['taskkill', '/F', '/T', '/IM', 'antigravity.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.attributes('-transparentcolor', 'magenta')
root.config(bg='magenta')

x = root.winfo_screenwidth() - 320
y = root.winfo_screenheight() - 120
root.geometry(f"+{x}+{y}")

canvas = tk.Canvas(root, width=300, height=90, bg='magenta', highlightthickness=0)
canvas.pack()

def create_round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y1+r, x2, y2-r, x2, y2-r, x2, y2, x2-r, y2, x2-r, y2, x1+r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y2-r, x1, y1+r, x1, y1+r, x1, y1]
    return canvas.create_polygon(points, **kwargs, smooth=True)

bg_idle = '#1e1e24'
border_idle = '#3a3a40'
pill = create_round_rect(canvas, 10, 10, 290, 80, r=20, fill=bg_idle, outline=border_idle, width=2)

brown = '#b87353'
black = '#000000'
sx, sy = 15, 10

# Thought Cloud Base (Smaller and shifted right)
cloud_color = '#2a2a32'
c_dot1 = canvas.create_oval(sx+55, sy+20, sx+63, sy+28, fill=cloud_color, outline='')
c_dot2 = canvas.create_oval(sx+70, sy+10, sx+80, sy+20, fill=cloud_color, outline='')

cx, cy = 115, 15
c_oval1 = canvas.create_oval(cx, cy+10, cx+40, cy+50, fill=cloud_color, outline='')
c_oval2 = canvas.create_oval(cx+20, cy, cx+80, cy+60, fill=cloud_color, outline='')
c_oval3 = canvas.create_oval(cx+60, cy+10, cx+110, cy+50, fill=cloud_color, outline='')
c_oval4 = canvas.create_oval(cx+40, cy-5, cx+100, cy+45, fill=cloud_color, outline='')
cloud_parts = (c_dot1, c_dot2, c_oval1, c_oval2, c_oval3, c_oval4)

# Face Base
body = canvas.create_rectangle(sx+15, sy+15, sx+65, sy+55, fill=brown, outline='')
arm_l = canvas.create_rectangle(sx+8, sy+30, sx+15, sy+45, fill=brown, outline='')
arm_r = canvas.create_rectangle(sx+65, sy+30, sx+72, sy+45, fill=brown, outline='')
leg1 = canvas.create_rectangle(sx+15, sy+55, sx+23, sy+70, fill=brown, outline='')
leg2 = canvas.create_rectangle(sx+28, sy+55, sx+36, sy+70, fill=brown, outline='')
leg3 = canvas.create_rectangle(sx+44, sy+55, sx+52, sy+70, fill=brown, outline='')
leg4 = canvas.create_rectangle(sx+57, sy+55, sx+65, sy+70, fill=brown, outline='')

eye_l = canvas.create_line(sx+22, sy+32, sx+30, sy+32, sx+30, sy+32, fill=black, width=3, joinstyle=tk.MITER)
eye_r = canvas.create_line(sx+58, sy+32, sx+50, sy+32, sx+50, sy+32, fill=black, width=3, joinstyle=tk.MITER)

face_parts = (body, arm_l, arm_r, leg1, leg2, leg3, leg4, eye_l, eye_r)

title_text = canvas.create_text(90, 45, text="Voila", fill="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")
status_text = canvas.create_text(cx+55, cy+25, text="Standing by...", fill="#888888", font=("Segoe UI", 9, "italic"), anchor="center")

close_btn = canvas.create_text(265, 45, text="✕", fill="#888888", font=("Segoe UI", 14, "bold"), anchor="center")

agent_process = subprocess.Popen(
    ["antigravity.exe", "--background"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    creationflags=CREATE_NO_WINDOW
)

def on_close(e=None):
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(agent_process.pid)], creationflags=CREATE_NO_WINDOW)
    root.destroy()
    sys.exit(0)

canvas.tag_bind(close_btn, '<Button-1>', on_close)

def on_enter_close(e): canvas.itemconfig(close_btn, fill="#ff5555")
def on_leave_close(e): canvas.itemconfig(close_btn, fill="#888888")
canvas.tag_bind(close_btn, '<Enter>', on_enter_close)
canvas.tag_bind(close_btn, '<Leave>', on_leave_close)


def start_move(e): root.x, root.y = e.x, e.y
def stop_move(e): root.x, root.y = None, None
def do_move(e): root.geometry(f"+{root.winfo_x() + (e.x - root.x)}+{root.winfo_y() + (e.y - root.y)}")

# DO NOT include close_btn in the drag bindings!
for item in [pill, title_text, status_text] + list(face_parts) + list(cloud_parts):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

ai_state = "IDLE"
mobile_clients = 1
anim_frame = 0
glow_timer = None

def update_expression():
    global ai_state
    if mobile_clients == 0:
        # SAD / DISCONNECTED
        canvas.itemconfig(pill, outline='#ff4444', fill='#2a1a1a')
        for cp in cloud_parts: canvas.itemconfig(cp, fill='#4a1a1a')
        canvas.itemconfig(status_text, text="Offline", fill='#ff8888')
        canvas.coords(eye_l, sx+22, sy+28, sx+30, sy+36, sx+30, sy+36) # \
        canvas.coords(eye_r, sx+58, sy+28, sx+50, sy+36, sx+50, sy+36) # /
        canvas.itemconfig(eye_l, fill='#ff4444')
        canvas.itemconfig(eye_r, fill='#ff4444')
    elif ai_state == "IDLE":
        # ASLEEP
        canvas.itemconfig(pill, outline='#3a3a40', fill='#1e1e24')
        for cp in cloud_parts: canvas.itemconfig(cp, fill='#2a2a32')
        canvas.itemconfig(status_text, text="Standing by...", fill='#888888')
        canvas.coords(eye_l, sx+22, sy+32, sx+30, sy+32, sx+30, sy+32)
        canvas.coords(eye_r, sx+58, sy+32, sx+50, sy+32, sx+50, sy+32)
        canvas.itemconfig(eye_l, fill=black)
        canvas.itemconfig(eye_r, fill=black)

def animation_loop():
    global anim_frame
    anim_frame += 1
    dots = "." * (anim_frame % 4)
    
    if mobile_clients > 0 and ai_state != "IDLE":
        canvas.itemconfig(pill, fill='#22222a')
        for cp in cloud_parts: canvas.itemconfig(cp, fill='#33333d')
        
        if ai_state == "THINKING":
            canvas.itemconfig(status_text, text=f"Thinking{dots}", fill='#ffffaa')
            canvas.itemconfig(pill, outline='#ffff55')
            # Look up!
            up = -4 if anim_frame % 2 == 0 else -6
            canvas.coords(eye_l, sx+24, sy+32+up, sx+30, sy+32+up, sx+30, sy+32+up)
            canvas.coords(eye_r, sx+56, sy+32+up, sx+50, sy+32+up, sx+50, sy+32+up)
            canvas.itemconfig(eye_l, fill='#ffff55')
            canvas.itemconfig(eye_r, fill='#ffff55')
            
        elif ai_state == "SEARCH":
            canvas.itemconfig(status_text, text=f"Search{dots}", fill='#aaffff')
            canvas.itemconfig(pill, outline='#00aaff')
            # Scan left and right
            offset = (anim_frame % 3) * 3
            canvas.coords(eye_l, sx+20+offset, sy+32, sx+28+offset, sy+32, sx+28+offset, sy+32)
            canvas.coords(eye_r, sx+52-offset, sy+32, sx+60-offset, sy+32, sx+60-offset, sy+32)
            canvas.itemconfig(eye_l, fill='#00aaff')
            canvas.itemconfig(eye_r, fill='#00aaff')
            
        elif ai_state == "BASH":
            canvas.itemconfig(status_text, text=f"Bash{dots}", fill='#aaffaa')
            canvas.itemconfig(pill, outline='#00ff44')
            # >_ shape, pulsing
            if anim_frame % 2 == 0:
                canvas.coords(eye_l, sx+22, sy+28, sx+30, sy+32, sx+22, sy+36) # >
                canvas.coords(eye_r, sx+50, sy+36, sx+58, sy+36, sx+58, sy+36) # _
            else:
                canvas.coords(eye_l, sx+24, sy+30, sx+30, sy+32, sx+24, sy+34)
                canvas.coords(eye_r, sx+52, sy+36, sx+56, sy+36, sx+56, sy+36)
            canvas.itemconfig(eye_l, fill='#00ff44')
            canvas.itemconfig(eye_r, fill='#00ff44')
            
        elif ai_state == "FILE":
            canvas.itemconfig(status_text, text=f"I/O{dots}", fill='#ffddaa')
            canvas.itemconfig(pill, outline='#ffaa00')
            # Reading motion (eyes darting)
            dart = (anim_frame % 4) * 2 - 2
            canvas.coords(eye_l, sx+24+dart, sy+30, sx+28+dart, sy+34, sx+24+dart, sy+30)
            canvas.coords(eye_r, sx+56+dart, sy+30, sx+52+dart, sy+34, sx+56+dart, sy+30)
            canvas.itemconfig(eye_l, fill='#ffaa00')
            canvas.itemconfig(eye_r, fill='#ffaa00')
            
        else: # Generic RUNNING
            canvas.itemconfig(status_text, text=f"Processing{dots}", fill='#aaffff')
            canvas.itemconfig(pill, outline='#00ffcc')
            if anim_frame % 2 == 0:
                canvas.coords(eye_l, sx+22, sy+26, sx+32, sy+32, sx+22, sy+38)
                canvas.coords(eye_r, sx+58, sy+26, sx+48, sy+32, sx+58, sy+38)
            else:
                canvas.coords(eye_l, sx+24, sy+28, sx+30, sy+32, sx+24, sy+36)
                canvas.coords(eye_r, sx+56, sy+28, sx+50, sy+32, sx+56, sy+36)
            canvas.itemconfig(eye_l, fill='#00ffcc')
            canvas.itemconfig(eye_r, fill='#00ffcc')
            
    root.after(150, animation_loop)

def reset_to_idle():
    global ai_state
    if ai_state != "IDLE":
        ai_state = "IDLE"
        update_expression()

def parse_line(line):
    global ai_state, mobile_clients, glow_timer
    
    if "STATUS: MOBILE_CLIENTS:" in line:
        count_str = line.split("STATUS: MOBILE_CLIENTS:")[1].strip()
        try:
            mobile_clients = int(count_str)
            update_expression()
        except: pass
        return
        
    if "STATUS: IDLE" in line:
        if glow_timer: root.after_cancel(glow_timer)
        glow_timer = root.after(1500, reset_to_idle)
        return
        
    if "STATUS: RUNNING" in line:
        if glow_timer: root.after_cancel(glow_timer)
        ai_state = "RUNNING"
        return
        
    # Real-time parsed stages
    l = line.lower()
    if "thinking" in l: ai_state = "THINKING"
    elif "search" in l: ai_state = "SEARCH"
    elif "command" in l or "powershell" in l: ai_state = "BASH"
    elif "read" in l or "write" in l or "edit" in l: ai_state = "FILE"

def read_output():
    while True:
        line = agent_process.stdout.readline()
        if not line: break
        line = line.strip()
        if line:
            root.after(0, parse_line, line)

t = threading.Thread(target=read_output, daemon=True)
t.start()
update_expression()
animation_loop()
root.mainloop()
