import tkinter as tk
import subprocess
import threading
import sys
import time

CREATE_NO_WINDOW = 0x08000000

subprocess.run(['taskkill', '/F', '/IM', 'antigravity.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.attributes('-transparentcolor', 'magenta')
root.config(bg='magenta')

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
x = screen_width - 320
y = screen_height - 120
root.geometry(f"+{x}+{y}")

canvas = tk.Canvas(root, width=300, height=90, bg='magenta', highlightthickness=0)
canvas.pack()

def create_round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = [
        x1+r, y1, x1+r, y1, x2-r, y1, x2-r, y1,
        x2, y1, x2, y1+r, x2, y1+r, x2, y2-r,
        x2, y2-r, x2, y2, x2-r, y2, x2-r, y2,
        x1+r, y2, x1+r, y2, x1, y2, x1, y2-r,
        x1, y2-r, x1, y1+r, x1, y1+r, x1, y1
    ]
    return canvas.create_polygon(points, **kwargs, smooth=True)

bg_idle = '#1e1e24'
bg_running = '#22222a'
border_idle = '#3a3a40'
border_running = '#00ffcc'

pill = create_round_rect(canvas, 10, 10, 290, 80, r=20, fill=bg_idle, outline=border_idle, width=2)

brown = '#b87353'
black = '#000000'
cyan = '#00ffcc'
white = '#ffffff'

sx = 15
sy = 10

# cld.webp Vector Face
body = canvas.create_rectangle(sx+15, sy+15, sx+65, sy+55, fill=brown, outline='')
arm_l = canvas.create_rectangle(sx+8, sy+30, sx+15, sy+45, fill=brown, outline='')
arm_r = canvas.create_rectangle(sx+65, sy+30, sx+72, sy+45, fill=brown, outline='')
leg1 = canvas.create_rectangle(sx+15, sy+55, sx+23, sy+70, fill=brown, outline='')
leg2 = canvas.create_rectangle(sx+28, sy+55, sx+36, sy+70, fill=brown, outline='')
leg3 = canvas.create_rectangle(sx+44, sy+55, sx+52, sy+70, fill=brown, outline='')
leg4 = canvas.create_rectangle(sx+57, sy+55, sx+65, sy+70, fill=brown, outline='')

# Dynamic Eyes (start as horizontal sleeping lines)
eye_l = canvas.create_line(sx+22, sy+32, sx+30, sy+32, sx+30, sy+32, fill=black, width=3, joinstyle=tk.MITER)
eye_r = canvas.create_line(sx+58, sy+32, sx+50, sy+32, sx+50, sy+32, fill=black, width=3, joinstyle=tk.MITER)

face_parts = (body, arm_l, arm_r, leg1, leg2, leg3, leg4, eye_l, eye_r)

title_text = canvas.create_text(95, 33, text="Voila", fill="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")
status_text = canvas.create_text(95, 53, text="Standing by...", fill="#888888", font=("Segoe UI", 10), anchor="w")

close_btn = canvas.create_text(265, 45, text="✕", fill="#888888", font=("Segoe UI", 14, "bold"), anchor="center")

agent_process = subprocess.Popen(
    ["antigravity.exe", "--background"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    creationflags=CREATE_NO_WINDOW
)

def on_close(event=None):
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(agent_process.pid)], creationflags=CREATE_NO_WINDOW)
    root.destroy()
    sys.exit(0)

canvas.tag_bind(close_btn, '<Button-1>', on_close)

def on_enter_close(e):
    canvas.itemconfig(close_btn, fill="#ff5555")
def on_leave_close(e):
    canvas.itemconfig(close_btn, fill="#888888")
canvas.tag_bind(close_btn, '<Enter>', on_enter_close)
canvas.tag_bind(close_btn, '<Leave>', on_leave_close)

def start_move(event):
    root.x = event.x
    root.y = event.y
def stop_move(event):
    root.x = None
    root.y = None
def do_move(event):
    new_x = root.winfo_x() + (event.x - root.x)
    new_y = root.winfo_y() + (event.y - root.y)
    root.geometry(f"+{new_x}+{new_y}")

for item in [pill, title_text, status_text] + list(face_parts):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

is_running = False
is_visually_running = False
glow_timer = None
anim_frame = 0

def update_visuals():
    global anim_frame
    if is_visually_running:
        canvas.itemconfig(pill, outline=border_running, fill=bg_running)
        canvas.itemconfig(status_text, fill=border_running)
    else:
        canvas.itemconfig(pill, outline=border_idle, fill=bg_idle)
        canvas.itemconfig(status_text, text="Standing by...", fill="#888888")
        # Reset dynamic eyes to asleep
        canvas.coords(eye_l, sx+22, sy+32, sx+30, sy+32, sx+30, sy+32)
        canvas.coords(eye_r, sx+58, sy+32, sx+50, sy+32, sx+50, sy+32)
        canvas.itemconfig(eye_l, fill=black)
        canvas.itemconfig(eye_r, fill=black)

def set_running(event=None):
    global is_visually_running, glow_timer
    is_visually_running = True
    if glow_timer:
        root.after_cancel(glow_timer)
    glow_timer = None
    update_visuals()

def turn_off_glow():
    global is_visually_running
    if not is_running:
        is_visually_running = False
        update_visuals()

def set_idle(event=None):
    global glow_timer
    if glow_timer:
        root.after_cancel(glow_timer)
    glow_timer = root.after(1500, turn_off_glow)

root.bind("<<Running>>", set_running)
root.bind("<<Idle>>", set_idle)

def animation_loop():
    global anim_frame
    if is_visually_running:
        anim_frame += 1
        dots = "." * (anim_frame % 4)
        canvas.itemconfig(status_text, text=f"Executing Task{dots}")
        
        # Dynamic Eyes Pattern for cld.webp!
        if anim_frame % 2 == 0:
            # Eyes wide open and glowing cyan
            canvas.coords(eye_l, sx+22, sy+26, sx+32, sy+32, sx+22, sy+38)
            canvas.coords(eye_r, sx+58, sy+26, sx+48, sy+32, sx+58, sy+38)
            canvas.itemconfig(eye_l, fill=cyan)
            canvas.itemconfig(eye_r, fill=cyan)
        else:
            # Eyes slightly squinted and glowing white
            canvas.coords(eye_l, sx+24, sy+28, sx+30, sy+32, sx+24, sy+36)
            canvas.coords(eye_r, sx+56, sy+28, sx+50, sy+32, sx+56, sy+36)
            canvas.itemconfig(eye_l, fill=white)
            canvas.itemconfig(eye_r, fill=white)
            
    root.after(150, animation_loop)

def read_output():
    global is_running
    while True:
        line = agent_process.stdout.readline()
        if not line:
            break
        line = line.strip()
        if "STATUS: RUNNING" in line:
            is_running = True
            root.event_generate("<<Running>>", when="tail")
        elif "STATUS: IDLE" in line:
            is_running = False
            root.event_generate("<<Idle>>", when="tail")

t = threading.Thread(target=read_output, daemon=True)
t.start()
animation_loop()
root.mainloop()
