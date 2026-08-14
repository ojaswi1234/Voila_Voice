import tkinter as tk
import subprocess
import threading
import sys

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

circle = canvas.create_oval(10, 10, 170, 170, fill='#1A1A24', outline=color_top, width=3)

# Glasses (Cyan)
left_glass = canvas.create_oval(45, 45, 80, 75, outline=color_top, width=5)
right_glass = canvas.create_oval(100, 45, 135, 75, outline=color_top, width=5)

# Jaw (Pink/Purple)
jaw = canvas.create_line(45, 85, 45, 120, 135, 120, 135, 85, fill=color_bottom, width=10, joinstyle=tk.ROUND)

# Nostrils / Eyes
nostril_L = canvas.create_rectangle(65, 95, 75, 105, fill=color_bottom, outline='')
nostril_R = canvas.create_rectangle(105, 95, 115, 105, fill=color_bottom, outline='')

status_text = canvas.create_text(90, 145, text='IDLE', fill=color_top, font=('Consolas', 12, 'bold'))

# Close button
btn_bg = canvas.create_oval(140, 15, 165, 40, fill='#FF5555', outline='white', width=1)
btn_text = canvas.create_text(152, 27, text='X', fill='white', font=('Arial', 12, 'bold'))

CREATE_NO_WINDOW = 0x08000000
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

for item in (circle, left_glass, right_glass, jaw, nostril_L, nostril_R, status_text):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

is_running = False
blink_state = False

def update_ui_state():
    global blink_state
    if is_running:
        canvas.itemconfig(circle, outline='#ff7b72', width=4)
        canvas.itemconfig(status_text, text='RUNNING', fill='#ff7b72')
        # Blink nostrils (they move up and turn red when running)
        blink_state = not blink_state
        if blink_state:
            canvas.coords(nostril_L, 65, 90, 75, 100)
            canvas.coords(nostril_R, 105, 90, 115, 100)
            canvas.itemconfig(nostril_L, fill='#ff7b72')
            canvas.itemconfig(nostril_R, fill='#ff7b72')
        else:
            canvas.coords(nostril_L, 65, 95, 75, 105)
            canvas.coords(nostril_R, 105, 95, 115, 105)
            canvas.itemconfig(nostril_L, fill=color_bottom)
            canvas.itemconfig(nostril_R, fill=color_bottom)
    else:
        canvas.itemconfig(circle, outline=color_top, width=3)
        canvas.itemconfig(status_text, text='IDLE', fill=color_top)
        canvas.coords(nostril_L, 65, 95, 75, 105)
        canvas.coords(nostril_R, 105, 95, 115, 105)
        canvas.itemconfig(nostril_L, fill=color_bottom)
        canvas.itemconfig(nostril_R, fill=color_bottom)

def animation_loop():
    if is_running:
        update_ui_state()
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
            root.after(0, update_ui_state)
        elif "STATUS: IDLE" in line:
            is_running = False
            root.after(0, update_ui_state)

t = threading.Thread(target=read_output, daemon=True)
t.start()

animation_loop()
root.mainloop()
