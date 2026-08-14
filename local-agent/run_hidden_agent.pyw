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
circle = canvas.create_oval(10, 10, 110, 110, fill='#1A1A24', outline='#3DDC97', width=2)
face_text = canvas.create_text(60, 52, text='╭─╮╭─╮\n╰─╯╰─╯\n█ ▘▝ █\n ▔▔▔▔', fill='white', font=('Consolas', 11, 'bold'), justify='center')
status_text = canvas.create_text(60, 90, text='IDLE', fill='#3DDC97', font=('Consolas', 9))

# Close button at top right (45 degrees)
btn_bg = canvas.create_oval(90, 10, 110, 30, fill='#FF5555', outline='white', width=1)
btn_text = canvas.create_text(100, 20, text='X', fill='white', font=('Arial', 10, 'bold'))

# Start Go agent hidden
CREATE_NO_WINDOW = 0x08000000
agent_process = subprocess.Popen(
    ["antigravity.exe"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    creationflags=CREATE_NO_WINDOW
)

def on_close():
    agent_process.terminate()
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

# Bind drag events to the circle and face
canvas.tag_bind(circle, "<ButtonPress-1>", start_move)
canvas.tag_bind(circle, "<ButtonRelease-1>", stop_move)
canvas.tag_bind(circle, "<B1-Motion>", do_move)
canvas.tag_bind(face_text, "<ButtonPress-1>", start_move)
canvas.tag_bind(face_text, "<ButtonRelease-1>", stop_move)
canvas.tag_bind(face_text, "<B1-Motion>", do_move)

# Animation state
is_running = False
anim_frame = 0
frames = [
    "╭─╮╭─╮\n╰─╯╰─╯\n█ ▘▝ █\n ▔▔▔▔",
    "╭─╮╭─╮\n╰─╯╰─╯\n█ ▀▀ █\n ▔▔▔▔",
    "╭─╮╭─╮\n╰─╯╰─╯\n█ ▗▖ █\n ▔▔▔▔",
    "╭─╮╭─╮\n╰─╯╰─╯\n█ >< █\n ▔▔▔▔",
]

def update_ui():
    global anim_frame
    if is_running:
        canvas.itemconfig(circle, outline='#FF007F', width=3)
        canvas.itemconfig(status_text, text='RUNNING', fill='#FF007F')
        canvas.itemconfig(face_text, text=frames[anim_frame % len(frames)])
        anim_frame += 1
    else:
        canvas.itemconfig(circle, outline='#3DDC97', width=2)
        canvas.itemconfig(status_text, text='IDLE', fill='#3DDC97')
        canvas.itemconfig(face_text, text='╭─╮╭─╮\n╰─╯╰─╯\n█ ▘▝ █\n ▔▔▔▔')
    root.after(400, update_ui)

def read_output():
    global is_running
    for line in agent_process.stdout:
        line = line.strip()
        print("AGENT:", line) # for debug if run in console
        if "STATUS: RUNNING" in line:
            is_running = True
        elif "STATUS: IDLE" in line:
            is_running = False

# Start reading thread
t = threading.Thread(target=read_output, daemon=True)
t.start()

# Start animation loop
update_ui()

root.mainloop()
