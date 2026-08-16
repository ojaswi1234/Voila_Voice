import tkinter as tk
import subprocess
import threading
import sys
import time
import math

CREATE_NO_WINDOW = 0x08000000
subprocess.run(['taskkill', '/F', '/T', '/IM', 'voila.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
subprocess.run(['taskkill', '/F', '/T', '/IM', 'ngrok.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

# Thought Cloud Base (Perfected layout: cx=150)
cloud_color = '#2a2a32'
c_dot1 = canvas.create_oval(90, 40, 95, 45, fill=cloud_color, outline='')
c_dot2 = canvas.create_oval(110, 30, 120, 40, fill=cloud_color, outline='')
c_dot3 = canvas.create_oval(130, 20, 145, 35, fill=cloud_color, outline='')

cx, cy = 150, 15
c_oval1 = canvas.create_oval(cx, cy+10, cx+40, cy+50, fill=cloud_color, outline='')
c_oval2 = canvas.create_oval(cx+20, cy, cx+80, cy+60, fill=cloud_color, outline='')
c_oval3 = canvas.create_oval(cx+60, cy+10, cx+110, cy+50, fill=cloud_color, outline='')
c_oval4 = canvas.create_oval(cx+40, cy-5, cx+100, cy+45, fill=cloud_color, outline='')
cloud_parts = (c_dot1, c_dot2, c_dot3, c_oval1, c_oval2, c_oval3, c_oval4)

# Face Base (x ends around 87)
body = canvas.create_rectangle(sx+15, sy+15, sx+65, sy+55, fill=brown, outline='')
arm_l = canvas.create_rectangle(sx+8, sy+30, sx+15, sy+45, fill=brown, outline='')
arm_r = canvas.create_rectangle(sx+65, sy+30, sx+72, sy+45, fill=brown, outline='')
leg1 = canvas.create_rectangle(sx+15, sy+55, sx+23, sy+70, fill=brown, outline='')
leg2 = canvas.create_rectangle(sx+28, sy+55, sx+36, sy+70, fill=brown, outline='')
leg3 = canvas.create_rectangle(sx+44, sy+55, sx+52, sy+70, fill=brown, outline='')
leg4 = canvas.create_rectangle(sx+57, sy+55, sx+65, sy+70, fill=brown, outline='')

# Base eyes now ovals instead of lines
eye_l = canvas.create_oval(sx+22, sy+28, sx+32, sy+38, fill=black, outline='')
eye_r = canvas.create_oval(sx+48, sy+28, sx+58, sy+38, fill=black, outline='')

# Shiny contrast reflections
eye_l_shine = canvas.create_oval(sx+27, sy+30, sx+30, sy+33, fill='white', outline='')
eye_r_shine = canvas.create_oval(sx+53, sy+30, sx+56, sy+33, fill='white', outline='')

# Snoring / Sleep visual elements
snot_bubble = canvas.create_oval(0, 0, 0, 0, fill='#aaddff', outline='#ffffff', state='hidden')
zzz1 = canvas.create_text(0, 0, text="Z", fill='#aaddff', font=("Segoe UI", 12, "bold"), state='hidden')
zzz2 = canvas.create_text(0, 0, text="z", fill='#aaddff', font=("Segoe UI", 10, "bold"), state='hidden')
zzz3 = canvas.create_text(0, 0, text="z", fill='#aaddff', font=("Segoe UI", 8, "bold"), state='hidden')

face_parts = (body, arm_l, arm_r, leg1, leg2, leg3, leg4, eye_l, eye_r, eye_l_shine, eye_r_shine, snot_bubble, zzz1, zzz2, zzz3)

# Perfectly positioned Title (x=90)
title_text = canvas.create_text(90, 45, text="Voila", fill="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")

# Perfectly centered status in the cloud (x=150+55=205)
status_text = canvas.create_text(cx+55, cy+25, text="Standing by...", fill="#888888", font=("Segoe UI", 9, "italic"), anchor="center")

# Close Button shifted right slightly to x=275
close_btn = canvas.create_text(275, 45, text="✕", fill="#888888", font=("Segoe UI", 14, "bold"), anchor="center")

agent_process = subprocess.Popen(
    ["voila.exe", "--background"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    creationflags=CREATE_NO_WINDOW
)

def on_close(e=None):
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(agent_process.pid)], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['taskkill', '/F', '/T', '/IM', 'voila.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['taskkill', '/F', '/T', '/IM', 'ngrok.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

# DO NOT bind close_btn to dragging!
for item in [pill, title_text, status_text] + list(face_parts) + list(cloud_parts):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

ai_state = "IDLE"
mobile_clients = 0
anim_frame = 0
glow_timer = None

def update_expression():
    global ai_state
    if mobile_clients == 0:
        # ASLEEP / OFFLINE
        canvas.itemconfig(pill, outline='#3a3a40', fill='#1e1e24')
        for cp in cloud_parts: canvas.itemconfig(cp, state='hidden')
        canvas.itemconfig(status_text, state='hidden')
        
        # Eyes closed (flatten the ovals into lines)
        canvas.coords(eye_l, sx+22, sy+34, sx+32, sy+36)
        canvas.coords(eye_r, sx+48, sy+34, sx+58, sy+36)
        canvas.itemconfig(eye_l, fill=black)
        canvas.itemconfig(eye_r, fill=black)
        
        # hide shine
        canvas.itemconfig(eye_l_shine, state='hidden')
        canvas.itemconfig(eye_r_shine, state='hidden')

    else:
        # NORMAL / IDLE / WORKING
        canvas.itemconfig(pill, outline='#3a3a40', fill='#1e1e24')
        for cp in cloud_parts: canvas.itemconfig(cp, state='normal', fill='#2a2a32')
        canvas.itemconfig(status_text, state='normal', text="Standing by...", fill='#888888')
        
        # Eyes normal
        canvas.coords(eye_l, sx+22, sy+28, sx+32, sy+38)
        canvas.coords(eye_r, sx+48, sy+28, sx+58, sy+38)
        canvas.itemconfig(eye_l, fill=black)
        canvas.itemconfig(eye_r, fill=black)
        
        # show shine
        canvas.itemconfig(eye_l_shine, state='normal')
        canvas.itemconfig(eye_r_shine, state='normal')
        canvas.coords(eye_l_shine, sx+27, sy+30, sx+30, sy+33)
        canvas.coords(eye_r_shine, sx+53, sy+30, sx+56, sy+33)
        
        # Hide sleep elements
        canvas.itemconfig(snot_bubble, state='hidden')
        canvas.itemconfig(zzz1, state='hidden')
        canvas.itemconfig(zzz2, state='hidden')
        canvas.itemconfig(zzz3, state='hidden')

def animation_loop():
    global anim_frame
    anim_frame += 1
    dots = "." * (anim_frame % 4)
    
    if mobile_clients == 0:
        # Animate Sleep Mode
        canvas.itemconfig(status_text, text=f"Offline (Zzz{dots})", fill='#888888')
        
        # Snot Bubble expansion/contraction
        canvas.itemconfig(snot_bubble, state='normal')
        bubble_phase = anim_frame % 16
        if bubble_phase < 8: br = 2 + bubble_phase
        else: br = 2 + (15 - bubble_phase)
        bx, by = sx+40, sy+40
        canvas.coords(snot_bubble, bx-br, by-br, bx+br, by+br)
        
        # Zzz flying animation
        canvas.itemconfig(zzz1, state='normal')
        canvas.itemconfig(zzz2, state='normal')
        canvas.itemconfig(zzz3, state='normal')
        
        z_phase = anim_frame % 24
        zx1, zy1 = bx + 10 + z_phase, by - 10 - z_phase
        canvas.coords(zzz1, zx1, zy1)
        
        z_phase2 = (anim_frame + 8) % 24
        zx2, zy2 = bx + 10 + z_phase2, by - 10 - z_phase2
        canvas.coords(zzz2, zx2, zy2)
        
        z_phase3 = (anim_frame + 16) % 24
        zx3, zy3 = bx + 10 + z_phase3, by - 10 - z_phase3
        canvas.coords(zzz3, zx3, zy3)

    elif ai_state != "IDLE":
        canvas.itemconfig(pill, fill='#22222a')
        canvas.itemconfig(status_text, state='normal')
        for cp in cloud_parts: canvas.itemconfig(cp, state='normal', fill='#33333d')
        
        # Pulse base size for expanding/contracting eyes
        pulse = (anim_frame % 6)
        if pulse > 3: pulse = 6 - pulse # 0, 1, 2, 3, 2, 1
        ew = 4 + pulse # radius 4 to 7
        
        elx, ely = sx+27, sy+33
        erx, ery = sx+53, sy+33
        
        canvas.coords(eye_l, elx-ew, ely-ew, elx+ew, ely+ew)
        canvas.coords(eye_r, erx-ew, ery-ew, erx+ew, ery+ew)
        
        # keep shine relative to eye center
        canvas.itemconfig(eye_l_shine, state='normal')
        canvas.itemconfig(eye_r_shine, state='normal')
        canvas.coords(eye_l_shine, elx, ely-3, elx+3, ely)
        canvas.coords(eye_r_shine, erx, ery-3, erx+3, ery)
        
        # State Colors
        if ai_state == "THINKING":
            canvas.itemconfig(status_text, text=f"Thinking{dots}", fill='#ffffaa')
            canvas.itemconfig(pill, outline='#ffff55')
            canvas.itemconfig(eye_l, fill='#ffff55')
            canvas.itemconfig(eye_r, fill='#ffff55')
        elif ai_state == "SEARCH":
            canvas.itemconfig(status_text, text=f"Search{dots}", fill='#aaffff')
            canvas.itemconfig(pill, outline='#00aaff')
            canvas.itemconfig(eye_l, fill='#00aaff')
            canvas.itemconfig(eye_r, fill='#00aaff')
        elif ai_state == "BASH":
            canvas.itemconfig(status_text, text=f"Bash{dots}", fill='#aaffaa')
            canvas.itemconfig(pill, outline='#00ff44')
            canvas.itemconfig(eye_l, fill='#00ff44')
            canvas.itemconfig(eye_r, fill='#00ff44')
        elif ai_state == "FILE":
            canvas.itemconfig(status_text, text=f"I/O{dots}", fill='#ffddaa')
            canvas.itemconfig(pill, outline='#ffaa00')
            canvas.itemconfig(eye_l, fill='#ffaa00')
            canvas.itemconfig(eye_r, fill='#ffaa00')
        else:
            canvas.itemconfig(status_text, text=f"Processing{dots}", fill='#aaffff')
            canvas.itemconfig(pill, outline='#00ffcc')
            canvas.itemconfig(eye_l, fill='#00ffcc')
            canvas.itemconfig(eye_r, fill='#00ffcc')
            
    elif ai_state == "IDLE":
        # Natural blinking animation every ~4.5 seconds (30 frames)
        blink_phase = anim_frame % 30
        if blink_phase == 0 or blink_phase == 1:
            # Eyes closed (flattened)
            canvas.coords(eye_l, sx+22, sy+32, sx+32, sy+34)
            canvas.coords(eye_r, sx+48, sy+32, sx+58, sy+34)
            canvas.itemconfig(eye_l_shine, state='hidden')
            canvas.itemconfig(eye_r_shine, state='hidden')
        else:
            # Eyes open
            canvas.coords(eye_l, sx+22, sy+28, sx+32, sy+38)
            canvas.coords(eye_r, sx+48, sy+28, sx+58, sy+38)
            canvas.itemconfig(eye_l_shine, state='normal')
            canvas.itemconfig(eye_r_shine, state='normal')
            
            cycle = anim_frame % 80
            px_offset, py_offset = 0, 0
            
            # 20 frames (3 sec): look at user (offset 0,0)
            # 60 frames (9 sec): track mouse
            if cycle >= 20:
                mx, my = root.winfo_pointerx(), root.winfo_pointery()
                ex = root.winfo_rootx() + sx + 27
                ey = root.winfo_rooty() + sy + 33
                dx, dy = mx - ex, my - ey
                dist = math.hypot(dx, dy)
                if dist > 0:
                    r = min(3.0, dist / 100.0)
                    px_offset = (dx / dist) * r
                    py_offset = (dy / dist) * r
            
            el_cx, el_cy = sx+27, sy+33
            er_cx, er_cy = sx+53, sy+33
            canvas.coords(eye_l_shine, el_cx+px_offset-1.5, el_cy+py_offset-1.5, el_cx+px_offset+1.5, el_cy+py_offset+1.5)
            canvas.coords(eye_r_shine, er_cx+px_offset-1.5, er_cy+py_offset-1.5, er_cx+px_offset+1.5, er_cy+py_offset+1.5)
            
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
        if line: root.after(0, parse_line, line)

t = threading.Thread(target=read_output, daemon=True)
t.start()
update_expression()
animation_loop()
root.mainloop()
