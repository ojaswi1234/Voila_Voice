import tkinter as tk
import subprocess
import threading
import sys
import time

CREATE_NO_WINDOW = 0x08000000

# Kill existing orphan agents
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

canvas = tk.Canvas(root, width=300, height=80, bg='magenta', highlightthickness=0)
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

pill = create_round_rect(canvas, 10, 10, 290, 70, r=20, fill=bg_idle, outline=border_idle, width=2)

color_top = '#79c0ff'
color_bottom = '#d2a8ff'

# Copilot Vector Face
glass_l = canvas.create_oval(25, 22, 42, 32, outline=color_top, width=2)
glass_r = canvas.create_oval(48, 22, 65, 32, outline=color_top, width=2)
jaw = canvas.create_line(28, 42, 28, 58, 62, 58, 62, 42, fill=color_bottom, width=6, joinstyle=tk.MITER)
eye_l = canvas.create_rectangle(36, 45, 40, 49, fill=color_bottom, outline='')
eye_r = canvas.create_rectangle(50, 45, 54, 49, fill=color_bottom, outline='')

title_text = canvas.create_text(85, 28, text="Voila Voice Agent", fill="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")
status_text = canvas.create_text(85, 48, text="Standing by...", fill="#888888", font=("Segoe UI", 10), anchor="w")

close_btn = canvas.create_text(265, 40, text="✕", fill="#888888", font=("Segoe UI", 14, "bold"), anchor="center")

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

for item in (pill, glass_l, glass_r, jaw, eye_l, eye_r, title_text, status_text):
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
        canvas.itemconfig(glass_l, outline=border_running)
        canvas.itemconfig(glass_r, outline=border_running)
        canvas.itemconfig(jaw, fill=border_running)
        canvas.itemconfig(eye_l, fill=border_running)
        canvas.itemconfig(eye_r, fill=border_running)
        canvas.itemconfig(status_text, fill=border_running)
    else:
        canvas.itemconfig(pill, outline=border_idle, fill=bg_idle)
        canvas.itemconfig(glass_l, outline=color_top)
        canvas.itemconfig(glass_r, outline=color_top)
        canvas.itemconfig(jaw, fill=color_bottom)
        canvas.itemconfig(eye_l, fill=color_bottom)
        canvas.itemconfig(eye_r, fill=color_bottom)
        canvas.itemconfig(status_text, text="Standing by...", fill="#888888")
        # Reset eye position
        canvas.coords(eye_l, 36, 45, 40, 49)
        canvas.coords(eye_r, 50, 45, 54, 49)

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
        
        # Copilot Vector Face Eye Animation (shifting dots left and right)
        if anim_frame % 2 == 0:
            canvas.coords(eye_l, 34, 45, 38, 49)
            canvas.coords(eye_r, 48, 45, 52, 49)
        else:
            canvas.coords(eye_l, 38, 45, 42, 49)
            canvas.coords(eye_r, 52, 45, 56, 49)
            
    root.after(300, animation_loop)

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
