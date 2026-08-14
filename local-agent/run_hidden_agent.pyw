import tkinter as tk
import subprocess
import threading
import sys
import os

# Create the bubble window
root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.attributes('-transparentcolor', 'magenta')
root.config(bg='magenta')

# Determine screen position (bottom right)
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
x = screen_width - 150
y = screen_height - 180
root.geometry(f"+{x}+{y}")

canvas = tk.Canvas(root, width=120, height=120, bg='magenta', highlightthickness=0)
canvas.pack()

# UI Elements
circle = canvas.create_oval(10, 10, 110, 110, fill='#1A1A24', outline='#79c0ff', width=2)

# Copilot Face (4 lines)
# Colors from image: Cyan/Blue top, Pink/Purple bottom
color_top = '#79c0ff'
color_bottom = '#d2a8ff'
font_style = ('Consolas', 11, 'bold')

line1 = canvas.create_text(60, 36, text='╭─╮╭─╮', fill=color_top, font=font_style)
line2 = canvas.create_text(60, 48, text='╰─╯╰─╯', fill=color_top, font=font_style)
line3 = canvas.create_text(60, 60, text='█ ▘▝ █', fill=color_bottom, font=font_style)
line4 = canvas.create_text(60, 72, text=' ▔▔▔▔ ', fill=color_bottom, font=font_style)

status_text = canvas.create_text(60, 95, text='IDLE', fill='#79c0ff', font=('Consolas', 9, 'bold'))

# Close button at top right (45 degrees)
btn_bg = canvas.create_oval(90, 10, 110, 30, fill='#FF5555', outline='white', width=1)
btn_text = canvas.create_text(100, 20, text='X', fill='white', font=('Arial', 10, 'bold'))

# Start Go agent hidden
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
    # Force kill process tree (including ngrok)
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(agent_process.pid)], creationflags=CREATE_NO_WINDOW)
    root.destroy()
    sys.exit(0)

canvas.tag_bind(btn_bg, '<Button-1>', lambda e: on_close())
canvas.tag_bind(btn_text, '<Button-1>', lambda e: on_close())

# Make window draggable
def start_move(event):
    root.x = event.x
    root.y = event.y

def stop_move(event):
    root.x = None
    root.y = None

def do_move(event):
    deltax = event.x - root.x
    deltay = event.y - root.y
    new_x = root.winfo_x() + deltax
    new_y = root.winfo_y() + deltay
    root.geometry(f"+{new_x}+{new_y}")

# Bind drag events
for item in (circle, line1, line2, line3, line4, status_text):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

# Animation state
is_running = False
anim_frame = 0
frames = ['█ ▘▝ █', '█ ▀▀ █', '█ ▗▖ █', '█ >< █']

def update_ui_state():
    global anim_frame
    if is_running:
        canvas.itemconfig(circle, outline='#ff7b72', width=3)
        canvas.itemconfig(status_text, text='RUNNING', fill='#ff7b72')
        canvas.itemconfig(line3, text=frames[anim_frame % len(frames)])
        anim_frame += 1
    else:
        canvas.itemconfig(circle, outline='#79c0ff', width=2)
        canvas.itemconfig(status_text, text='IDLE', fill='#79c0ff')
        canvas.itemconfig(line3, text='█ ▘▝ █')

def animation_loop():
    if is_running:
        update_ui_state()
    root.after(400, animation_loop)

def read_output():
    global is_running
    while True:
        line = agent_process.stdout.readline()
        if not line:
            break
        line = line.strip()
        
        if "STATUS: RUNNING" in line:
            is_running = True
            root.after(0, update_ui_state) # Update immediately
        elif "STATUS: IDLE" in line:
            is_running = False
            root.after(0, update_ui_state) # Update immediately

# Start reading thread
t = threading.Thread(target=read_output, daemon=True)
t.start()

# Start animation loop
animation_loop()

root.mainloop()
