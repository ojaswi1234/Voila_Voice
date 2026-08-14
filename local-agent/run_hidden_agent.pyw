import tkinter as tk
import subprocess
import threading
import sys
import time

CREATE_NO_WINDOW = 0x08000000

# Kill any existing orphan agents to ensure we own the active agent
subprocess.run(['taskkill', '/F', '/IM', 'antigravity.exe'], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)

root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.attributes('-transparentcolor', 'magenta')
root.config(bg='magenta')

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
x = screen_width - 200
y = screen_height - 220
root.geometry(f"+{x}+{y}")

canvas = tk.Canvas(root, width=180, height=180, bg='magenta', highlightthickness=0)
canvas.pack()

# UI Elements
color_top = '#79c0ff'
color_bottom = '#d2a8ff'
font_style = ('Consolas', 18, 'normal')

circle = canvas.create_oval(10, 10, 170, 170, fill='#1A1A24', outline=color_top, width=3)

# EXACT ASCII ART layered to touch vertically
line1 = canvas.create_text(90, 50, text='╭─╮╭─╮', fill=color_top, font=font_style, anchor='n')
line2 = canvas.create_text(90, 62, text='╰─╯╰─╯', fill=color_top, font=font_style, anchor='n')
line3 = canvas.create_text(90, 75, text='█ ▘▝ █', fill=color_bottom, font=font_style, anchor='n')
line4 = canvas.create_text(90, 89, text=' ▔▔▔▔ ', fill=color_bottom, font=font_style, anchor='n')

status_text = canvas.create_text(90, 145, text='IDLE', fill=color_top, font=('Consolas', 12, 'bold'))

btn_bg = canvas.create_oval(140, 15, 165, 40, fill='#FF5555', outline='white', width=1)
btn_text = canvas.create_text(152, 27, text='X', fill='white', font=('Arial', 12, 'bold'))

agent_process = subprocess.Popen(
    ["antigravity.exe", "--background"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    creationflags=CREATE_NO_WINDOW
)

def on_close():
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(agent_process.pid)], creationflags=CREATE_NO_WINDOW)
    root.destroy()
    sys.exit(0)

canvas.tag_bind(btn_bg, '<Button-1>', lambda e: on_close())
canvas.tag_bind(btn_text, '<Button-1>', lambda e: on_close())

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

for item in (circle, line1, line2, line3, line4, status_text):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

is_running = False
is_visually_running = False
glow_timer = None
blink_state = False

def update_visuals():
    if is_visually_running:
        canvas.itemconfig(circle, outline='#ff7b72', width=4)
        canvas.itemconfig(status_text, text='RUNNING', fill='#ff7b72')
        # Animation loop will handle line3
    else:
        canvas.itemconfig(circle, outline=color_top, width=3)
        canvas.itemconfig(status_text, text='IDLE', fill=color_top)
        canvas.itemconfig(line3, text='█ ▘▝ █')

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
    glow_timer = root.after(1500, turn_off_glow) # Glow stays for at least 1.5 seconds

root.bind("<<Running>>", set_running)
root.bind("<<Idle>>", set_idle)

def animation_loop():
    global blink_state
    if is_visually_running:
        blink_state = not blink_state
        if blink_state:
            canvas.itemconfig(line3, text='█ ▀▀ █', fill='#ff7b72')
        else:
            canvas.itemconfig(line3, text='█ ▗▖ █', fill='#ff7b72')
    else:
        canvas.itemconfig(line3, fill=color_bottom)
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
