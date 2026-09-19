import tkinter as tk
import tkinter.messagebox
from tkinter import ttk
import subprocess
import threading
import sys
import time
import math
import random

import ctypes

import ctypes

_job_handle = None

def _assign_process_to_job(pid):
    global _job_handle
    try:
        kernel32 = ctypes.windll.kernel32
        
        # Create Job Object if not exists
        if _job_handle is None:
            _job_handle = kernel32.CreateJobObjectW(None, None)
            
            # Setup limits
            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                            ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
                            ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32),
                            ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32),
                            ('SchedulingClass', ctypes.c_uint32)]
            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [('ReadOperationCount', ctypes.c_uint64), ('WriteOperationCount', ctypes.c_uint64),
                            ('OtherOperationCount', ctypes.c_uint64), ('ReadTransferCount', ctypes.c_uint64),
                            ('WriteTransferCount', ctypes.c_uint64), ('OtherTransferCount', ctypes.c_uint64)]
            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION), ('IoInfo', IO_COUNTERS),
                            ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                            ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
            
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            
            kernel32.SetInformationJobObject(_job_handle, 9, ctypes.byref(info), ctypes.sizeof(info))
        
        # Assign process
        process = kernel32.OpenProcess(0x0100 | 0x0001, False, pid) # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if process:
            kernel32.AssignProcessToJobObject(_job_handle, process)
            kernel32.CloseHandle(process)
    except Exception as e:
        print("Job object assignment failed:", e)


# Prevent Windows Screen/System sleep (like a YouTube video)
try:
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)
except Exception:
    pass


# Removed psutil import completely as per user request to drop overhead
PSUTIL_AVAILABLE = False

import logging as _logging
_voila_log = _logging.getLogger('voila_py')
_voila_log.setLevel(_logging.DEBUG)
_voila_fh = _logging.FileHandler(
    r'C:\Users\ojasw\Desktop\Voila_Voice\local-agent\voila_debug.log',
    encoding='utf-8'
)
_voila_fh.setFormatter(_logging.Formatter('%(asctime)s [PY] %(message)s'))
_voila_log.addHandler(_voila_fh)
_voila_log.info(f'Python widget started PID={__import__("os").getpid()}')

CREATE_NO_WINDOW = 0x08000000
# Only kill the specific voila.exe instance we'll start, not all instances
# Don't kill ngrok.exe as it might be used by other applications
time.sleep(1)

root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.attributes('-transparentcolor', 'magenta')
root.config(bg='magenta')

x = (root.winfo_screenwidth() - 240) // 2
y = 20
root.geometry(f"+{x}+{y}")

canvas = tk.Canvas(root, width=240, height=65, bg='magenta', highlightthickness=0)
canvas.pack()

def create_round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    points = round_rect_points(x1, y1, x2, y2, r)
    return canvas.create_polygon(points, **kwargs, smooth=True)

def round_rect_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
        x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1,
    ]

def set_round_rect(item_id, x1, y1, x2, y2, r=20):
    canvas.coords(item_id, *round_rect_points(x1, y1, x2, y2, r))

bg_idle = '#18181b' # Obsidian background
border_idle = '#27272a'
pill = create_round_rect(canvas, 5, 5, 235, 60, r=27, fill=bg_idle, outline=border_idle, width=2)

cx, cy = 35, 30 # Core center

import math

def update_3d_ring(canvas, ring_id, cx, cy, radius, rot_x, rot_y, rot_z, scale, shadow_id=None, shadow_offset=0):
    points = []
    steps = 100
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        z = 0
        y1 = y * math.cos(rot_x) - z * math.sin(rot_x)
        z1 = y * math.sin(rot_x) + z * math.cos(rot_x)
        x2 = x * math.cos(rot_y) + z1 * math.sin(rot_y)
        z2 = -x * math.sin(rot_y) + z1 * math.cos(rot_y)
        x3 = x2 * math.cos(rot_z) - y1 * math.sin(rot_z)
        y3 = x2 * math.sin(rot_z) + y1 * math.cos(rot_z)
        points.extend((cx + x3 * scale, cy + y3 * scale))

    # Append first point again to close the loop smoothly
    points.extend((points[0], points[1]))

    canvas.coords(ring_id, *points)
    
    if shadow_id:
        sh_pts = []
        for i in range(0, len(points), 2):
            sh_pts.extend((points[i], points[i+1] + shadow_offset))
        canvas.coords(shadow_id, *sh_pts)

# Shadows (drawn first so they are at the bottom)
shadow1 = canvas.create_line(0,0, 0,0, fill='#000000', width=1.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
shadow2 = canvas.create_line(0,0, 0,0, fill='#000000', width=1.5, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
shadow3 = canvas.create_line(0,0, 0,0, fill='#000000', width=2.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)

# Hyperrealistic Dyson Sphere Sun Glow layers
sun_aura = canvas.create_oval(cx-26, cy-26, cx+26, cy+26, fill='#1e1e24', outline='')
sun_glow4 = canvas.create_oval(cx-22, cy-22, cx+22, cy+22, fill='#27272a', outline='')
sun_glow3 = canvas.create_oval(cx-18, cy-18, cx+18, cy+18, fill='#3f3f46', outline='')
sun_glow2 = canvas.create_oval(cx-14, cy-14, cx+14, cy+14, fill='#52525b', outline='')
sun_glow1 = canvas.create_oval(cx-10, cy-10, cx+10, cy+10, fill='#a1a1aa', outline='')
core_bg = canvas.create_oval(cx-6, cy-6, cx+6, cy+6, fill='#ffffff', outline='')

# Front Rings (drawn over the sun)
core_arc1 = canvas.create_line(0,0, 0,0, fill='#06b6d4', width=1.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
core_arc2 = canvas.create_line(0,0, 0,0, fill='#3b82f6', width=1.5, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
core_arc3 = canvas.create_line(0,0, 0,0, fill='#0ea5e9', width=2.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)

# Special State Icons (hidden by default)
term_prompt = canvas.create_text(cx, cy, text=">_", fill="#10b981", font=("Consolas", 11, "bold"), state="hidden")
file_icon = canvas.create_polygon(cx-8, cy-10, cx+4, cy-10, cx+10, cy-4, cx+10, cy+12, cx-8, cy+12, fill="", outline="#6366f1", width=2, state="hidden")
radar_arc = canvas.create_arc(cx-22, cy-22, cx+22, cy+22, start=0, extent=60, outline="#3b82f6", fill="", width=3, style=tk.ARC, state="hidden")
browser_box = canvas.create_rectangle(cx-12, cy-10, cx+12, cy+10, fill="", outline="#f97316", width=2, state="hidden")
browser_line = canvas.create_line(cx-12, cy-4, cx+12, cy-4, fill="#f97316", width=2, state="hidden")

# Keep variables compatible with animation loop
face_parts = (shadow1, shadow2, shadow3, sun_aura, sun_glow4, sun_glow3, sun_glow2, sun_glow1, core_bg, core_arc1, core_arc2, core_arc3, term_prompt, file_icon, radar_arc, browser_box, browser_line)
cloud_parts = () # Empty, we don't use a thought cloud anymore

# Typography Layout
title_text = canvas.create_text(70, 24, text="Voila AI", fill="#f3f4f6", font=("Segoe UI", 12, "bold"), anchor="w")

# Mode Badge
mode_badge_bg = create_round_rect(canvas, 145, 16, 195, 32, r=6, fill='#27272a', outline='', width=0)
mode_badge_text = canvas.create_text(170, 24, text="LOCAL", fill="#9ca3af", font=("Segoe UI", 8, "bold"), anchor="center")

# Status Text (Sleek text below title)
status_text = canvas.create_text(70, 44, text="Standing by...", fill="#9ca3af", font=("Segoe UI", 9), anchor="w", width=130)

# Minimalist Close Button
close_btn_bg = canvas.create_oval(205, 22, 225, 42, fill="", outline="", width=0, state='normal')
close_btn = canvas.create_text(215, 32, text="✖", fill="#6b7280", font=("Segoe UI", 10, "bold"), anchor="center")

# ─── LOCAL/CLOUD mode toggle  ────────────────────────────────────────────
MODES = ["LOCAL", "GROQ", "OLLAMA"]
MODE_COLORS = {"LOCAL": "#6366F1", "GROQ": "#10B981", "OLLAMA": "#F59E0B"}
MODE_LABELS = {"LOCAL": "⚡LOCAL", "GROQ": "☕ GROQ", "OLLAMA": "🦙 OLLAMA"}
current_mode = "LOCAL"

# Fetch saved mode from Go backend on startup
def _fetch_saved_mode():
    global current_mode
    import urllib.request, json, time, threading
    def _do():
        for _ in range(10): # retry for 5 seconds
            try:
                req = urllib.request.Request("http://localhost:8088/api-keys")
                with urllib.request.urlopen(req, timeout=1) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("active_mode"):
                        global current_mode
                        current_mode = data["active_mode"]
                    break # success, exit loop
            except Exception:
                time.sleep(0.5)
    threading.Thread(target=_do, daemon=True).start()
    
_fetch_saved_mode()

def _set_voila_mode(mode):
    def _do():
        try:
            import urllib.request as _ur, json as _j
            data = _j.dumps({"mode": mode}).encode()
            req = _ur.Request("http://localhost:8088/set-mode", data=data,
                              headers={"Content-Type": "application/json"}, method="POST")
            _ur.urlopen(req, timeout=3)
        except: pass
    import threading as _t
    _t.Thread(target=_do, daemon=True).start()

import os as _os
_agent_env = _os.environ.copy()
# Bug #16 Fix: When stdout is piped (not a TTY), the Go runtime switches to 4KB
# block-buffering, delaying STATUS: messages by seconds. Setting GOLOG_UNBUFFERED=1
# is not a standard flag, but we can force Python-side line-by-line reading and
# also set a custom env flag that the Go code checks to call os.Stdout.Sync()
# after each fmt.Println. Until Go binary is rebuilt, we use bufsize=1 + universal_newlines.
_agent_env["VOILA_UNBUFFERED"] = "1"  # The Go binary reads this and calls Sync() after prints

agent_process = subprocess.Popen(
    ["voila.exe", "--background"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,           # Line-buffered on Python side
    env=_agent_env,
    creationflags=CREATE_NO_WINDOW
)
_assign_process_to_job(agent_process.pid)

import atexit

def cleanup_processes():
    try:
        # Only kill the specific voila.exe instance we started
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(agent_process.pid)], creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass

atexit.register(cleanup_processes)

def on_close(e=None):
    if dashboard_active:
        close_dashboard()
    else:
        cleanup_processes()
        root.destroy()
        sys.exit(0)

is_hovering_pill = False
def on_enter_pill(e): 
    global is_hovering_pill
    is_hovering_pill = True
    
def on_leave_pill(e): 
    global is_hovering_pill
    is_hovering_pill = False

def on_enter_close(e):
    if dashboard_active:
        try:
            canvas.itemconfig("close_btn_bg", fill="#DC2626", outline="#B91C1C")  # Darker red on hover
        except:
            pass
    else:
        canvas.itemconfig(close_btn_bg, fill="#DC2626", outline="#B91C1C")  # Darker red on hover
        canvas.itemconfig(close_btn, fill="#FFFFFF")

def on_leave_close(e):
    if dashboard_active:
        try:
            canvas.itemconfig("close_btn_bg", fill="#EF4444", outline="#DC2626")  # Restore red
        except:
            pass
    else:
        canvas.itemconfig(close_btn_bg, fill="#EF4444", outline="#DC2626")  # Restore red
        canvas.itemconfig(close_btn, fill="#FFFFFF")

def switch_section(section):
    """Switch dashboard section (frame-based UI)."""
    global current_section
    if section == current_section:
        return
    current_section = section
    refresh_dashboard_content()

# Bind both close button elements for better click detection
canvas.tag_bind(close_btn, '<Button-1>', on_close)
canvas.tag_bind(close_btn_bg, '<Button-1>', on_close)
canvas.tag_bind(close_btn, '<Enter>', on_enter_close)
canvas.tag_bind(close_btn_bg, '<Enter>', on_enter_close)
canvas.tag_bind(close_btn, '<Leave>', on_leave_close)
canvas.tag_bind(close_btn_bg, '<Leave>', on_leave_close)

def start_move(e):
    if dashboard_active or dashboard_transition_in_progress:
        return
    root.x, root.y = e.x, e.y

def stop_move(e):
    if dashboard_active or dashboard_transition_in_progress:
        return
    root.x, root.y = None, None

def do_move(e):
    if dashboard_active or dashboard_transition_in_progress:
        return
    root.geometry(f"+{root.winfo_x() + (e.x - root.x)}+{root.winfo_y() + (e.y - root.y)}")

# DO NOT bind close_btn to dragging!
# Remove pill from draggable items to allow click to work
for item in [title_text, status_text] + list(face_parts) + list(cloud_parts):
    canvas.tag_bind(item, "<ButtonPress-1>", start_move)
    canvas.tag_bind(item, "<ButtonRelease-1>", stop_move)
    canvas.tag_bind(item, "<B1-Motion>", do_move)

# Pill is now only for dashboard toggle, not dragging
canvas.tag_bind(pill, '<Button-1>', lambda e: toggle_dashboard())  # Click AI face to toggle dashboard
canvas.tag_bind(pill, '<Enter>', on_enter_pill)
canvas.tag_bind(pill, '<Leave>', on_leave_pill)

ai_state = "IDLE"
mobile_clients = 0
backend_status = 'Active'
anim_frame = 0
current_rendered_state = "IDLE"
transition_scale = 1.0
transitioning = False
typewriter_idx = 0
typewriter_base = ""
typewriter_target = ""
glow_timer = None

# Resource alert state
alert_state = {
    "active": False,
    "message": "",
    "apps": [],
    "alert_timer": None,
    "alert_duration": 0,
    "last_alert_time": 0,
    "alert_cooldown": 15,  # Minimum seconds between alerts
    "state_changed": False  # Flag to trigger expression update
}

# Dynamic sizing
current_width = 240
current_height = 65
target_width = 240
target_height = 65
transition_progress = 0.0
transition_in_progress = False

# Resource monitoring functions removed to drop overhead

def update_expression():
    global ai_state, alert_state
    if dashboard_active or dashboard_transition_in_progress:
        return
        
    if alert_state["active"]:
        alert_msg = alert_state["message"]
        apps = alert_state["apps"]
        if apps:
            alert_msg += "\n• " + "\n• ".join(apps)
        canvas.itemconfig(status_text, state='normal', text=alert_msg, fill='#ef4444', font=("Segoe UI", 9, "bold"))
        canvas.itemconfig(pill, outline='#ef4444', fill='#450a0a')
        
        if current_width != target_width:
            canvas.itemconfig(status_text, width=max(150, target_width - 120))
    else:
        # Reset is handled by animation_loop automatically
        pass

# Dashboard state (separate from alert resizing to avoid conflicts)
dashboard_active = False
dashboard_transition_in_progress = False
dashboard_transition_progress = 0.0
original_pos = ((root.winfo_screenwidth() - 240) // 2, 20)  # Store original position
original_size = (240, 65)  # Store original size
usage_stats = {
    "commands_executed": 0,
    "commands_successful": 0,
    "commands_failed": 0,
    "avg_latency_ms": 45,  # Initial simulated latency
    "session_start": time.time(),
    "last_command_time": 0,
    "peak_commands_per_min": 0,
    "timeline_data": []  # Store performance timeline data
}
current_section = "Dashboard"  # Current active section
heatmap_cache = None
DASHBOARD_W = 1050
DASHBOARD_H = 620
simulated_dash_time = 0.0

def hide_mini_popup_elements():
    """Hide mini widget canvas while dashboard is shown."""
    canvas.pack_forget()

def restore_mini_popup_elements(w=240, h=65):
    """Fully restore the compact widget layout and styling."""
    global cx, cy, heatmap_cache, current_width, current_height

    cx, cy = 35, 30
    heatmap_cache = None
    current_width = w
    current_height = h

    canvas.config(bg='magenta', width=w, height=h)
    canvas.pack(fill='both', expand=True)

    set_round_rect(pill, 5, 5, w - 5, h - 5, 27)
    canvas.itemconfig(pill, state='normal', fill=bg_idle, outline=border_idle, width=2)

    canvas.coords(core_bg, cx-20, cy-20, cx+20, cy+20)
    canvas.coords(core_arc1, cx-20, cy-20, cx+20, cy+20)
    canvas.coords(core_arc2, cx-15, cy-15, cx+15, cy+15)
    canvas.coords(core_arc3, cx-25, cy-25, cx+25, cy+25)
    
    canvas.coords(term_prompt, cx, cy)
    canvas.coords(file_icon, cx-8, cy-10, cx+4, cy-10, cx+10, cy-4, cx+10, cy+12, cx-8, cy+12)
    canvas.coords(radar_arc, cx-22, cy-22, cx+22, cy+22)
    canvas.coords(browser_box, cx-12, cy-10, cx+12, cy+10)
    canvas.coords(browser_line, cx-12, cy-4, cx+12, cy-4)

    canvas.coords(title_text, 70, 24)
    canvas.itemconfig(title_text, state='normal', fill="#f3f4f6", font=("Segoe UI", 12, "bold"))

    set_round_rect(mode_badge_bg, 145, 16, 195, 32, 6)
    canvas.coords(mode_badge_text, 170, 24)
    
    canvas.coords(status_text, 70, 44)
    canvas.itemconfig(status_text, state='normal', width=130, fill="#9ca3af", font=("Segoe UI", 9))

    canvas.coords(close_btn_bg, 205, 22, 225, 42)
    canvas.itemconfig(close_btn_bg, state='normal', fill="", outline="")
    canvas.coords(close_btn, 215, 32)
    canvas.itemconfig(close_btn, state='normal', fill="#6b7280", font=("Segoe UI", 10, "bold"))
    
    # Ensure they are clickable above the pill
    canvas.tag_raise(close_btn_bg)
    canvas.tag_raise(close_btn)

    update_expression()

# --- Dashboard frame UI (separate from mini popup canvas) ---
dashboard_frame = tk.Frame(root, bg='#0F1115')
dash_body = tk.Frame(dashboard_frame, bg='#0F1115')
dash_sidebar = tk.Frame(dash_body, bg='#16171C', width=170)
dash_sidebar.pack_propagate(False)
dash_content = tk.Frame(dash_body, bg='#0F1115')
dash_title_var = tk.StringVar(value='Dashboard')
dash_session_var = tk.StringVar(value='0m')
nav_btn_widgets = {}
dash_canvas = None
_dashboard_ui_built = False

NAV_ITEMS = [
    ('Dashboard', 'Dashboard'),
    ('Connections', 'Connect'),
    ('Analytics', 'Analytics'),
    ('Settings', 'Settings'),
    
    ('Teams', 'Teams'),
]

def _style_nav_button(section):
    btn = nav_btn_widgets.get(section)
    if not btn:
        return
    if section == current_section:
        btn.configure(bg='#1F2128', fg='#FFFFFF', font=('Segoe UI', 9, 'bold'), activebackground='#1F2128', activeforeground='#FFFFFF')
    else:
        btn.configure(bg='#16171C', fg='#9CA3AF', font=('Segoe UI', 9), activebackground='#252528', activeforeground='#FFFFFF')

dash_sphere_canvas = None
dash_sphere_parts = {}

def init_dash_sphere():
    global dash_sphere_canvas, dash_sphere_parts
    if dash_sphere_canvas: return
    dash_sphere_canvas = tk.Canvas(dash_sidebar, width=120, height=120, bg='#16171C', highlightthickness=0)
    dash_sphere_canvas.pack(pady=(16, 0))
    c = dash_sphere_canvas
    dash_sphere_parts['shadow1'] = c.create_line(0,0, 0,0, fill='#000000', width=1.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
    dash_sphere_parts['shadow2'] = c.create_line(0,0, 0,0, fill='#000000', width=1.5, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
    dash_sphere_parts['shadow3'] = c.create_line(0,0, 0,0, fill='#000000', width=2.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
    dash_sphere_parts['sun_aura'] = c.create_oval(0,0,0,0, fill='#1e1e24', outline='')
    dash_sphere_parts['sun_glow4'] = c.create_oval(0,0,0,0, fill='#27272a', outline='')
    dash_sphere_parts['sun_glow3'] = c.create_oval(0,0,0,0, fill='#3f3f46', outline='')
    dash_sphere_parts['sun_glow2'] = c.create_oval(0,0,0,0, fill='#52525b', outline='')
    dash_sphere_parts['sun_glow1'] = c.create_oval(0,0,0,0, fill='#a1a1aa', outline='')
    dash_sphere_parts['core_bg'] = c.create_oval(0,0,0,0, fill='#ffffff', outline='')
    dash_sphere_parts['core_arc1'] = c.create_line(0,0, 0,0, fill='#06b6d4', width=1.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
    dash_sphere_parts['core_arc2'] = c.create_line(0,0, 0,0, fill='#3b82f6', width=1.5, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)
    dash_sphere_parts['core_arc3'] = c.create_line(0,0, 0,0, fill='#0ea5e9', width=2.0, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)

def update_dash_sphere(pulse, r1_x, r1_y, r1_z, r2_x, r2_y, r2_z, r3_x, r3_y, r3_z):
    if not dash_sphere_canvas: return
    c = dash_sphere_canvas
    p = dash_sphere_parts
    cx, cy = 60, 60
    scale = 2.0
    
    # Ensure they are visible (handles the bug where hidden state gets applied to the wrong canvas)
    for key in p:
        try: c.itemconfig(p[key], state='normal')
        except: pass

    c.coords(p['sun_aura'], cx-(26+pulse*1.2)*scale, cy-(26+pulse*1.2)*scale, cx+(26+pulse*1.2)*scale, cy+(26+pulse*1.2)*scale)
    c.coords(p['sun_glow4'], cx-(22+pulse*1.0)*scale, cy-(22+pulse*1.0)*scale, cx+(22+pulse*1.0)*scale, cy+(22+pulse*1.0)*scale)
    c.coords(p['sun_glow3'], cx-(18+pulse*0.8)*scale, cy-(18+pulse*0.8)*scale, cx+(18+pulse*0.8)*scale, cy+(18+pulse*0.8)*scale)
    c.coords(p['sun_glow2'], cx-(14+pulse*0.6)*scale, cy-(14+pulse*0.6)*scale, cx+(14+pulse*0.6)*scale, cy+(14+pulse*0.6)*scale)
    c.coords(p['sun_glow1'], cx-(10+pulse*0.3)*scale, cy-(10+pulse*0.3)*scale, cx+(10+pulse*0.3)*scale, cy+(10+pulse*0.3)*scale)
    c.coords(p['core_bg'], cx-(6)*scale, cy-(6)*scale, cx+(6)*scale, cy+(6)*scale)
    update_3d_ring(c, p['core_arc1'], cx, cy, 14, r1_x, r1_y, r1_z, scale, p['shadow1'], 2*scale)
    update_3d_ring(c, p['core_arc2'], cx, cy, 17, r2_x, r2_y, r2_z, scale, p['shadow2'], 2*scale)
    update_3d_ring(c, p['core_arc3'], cx, cy, 20, r3_x, r3_y, r3_z, scale, p['shadow3'], 2*scale)
    
    # Force redraw
    c.update_idletasks()
    
    # Force redraw
    c.update_idletasks()


def build_dashboard_ui():
    global _dashboard_ui_built, dash_canvas
    if _dashboard_ui_built:
        return
    _dashboard_ui_built = True

    header = tk.Frame(dashboard_frame, bg='#0F1115')
    header.pack(fill='x', padx=16, pady=(10, 0))

    tk.Label(header, textvariable=dash_title_var, bg='#0F1115', fg='#FFFFFF', font=('Segoe UI', 18, 'bold')).pack(side='left')
    tk.Label(header, textvariable=dash_session_var, bg='#0F1115', fg='#6B7280', font=('Segoe UI', 10)).pack(side='right')

    close_dash = tk.Button(
        header, text='✖', command=toggle_dashboard,
        bg='#EF4444', fg='#FFFFFF', activebackground='#DC2626', activeforeground='#FFFFFF',
        relief='flat', bd=0, width=3, font=('Segoe UI', 12, 'bold'), cursor='hand2',
    )
    close_dash.pack(side='right', padx=(0, 8))

    # ─── Mode Toggle Pill (in dashboard header) ────────────────────────────────
    _mode_toggle_frame = tk.Frame(header, bg='#1A1D23', bd=0, relief='flat')
    _mode_toggle_frame.pack(side='right', padx=(0, 16))

    _dash_mode_btns = {}

    def _switch_mode_btn(new_mode):
        global current_mode
        current_mode = new_mode
        _set_voila_mode(new_mode)
        # Refresh button highlights
        for m, btn in _dash_mode_btns.items():
            if m == current_mode:
                btn.config(bg=MODE_COLORS[m], fg='#FFFFFF')
            else:
                btn.config(bg='#2D3039', fg='#9CA3AF')

    for m in MODES:
        is_active = (m == current_mode)
        b = tk.Button(
            _mode_toggle_frame, text=MODE_LABELS[m],
            bg=MODE_COLORS[m] if is_active else '#2D3039',
            fg='#FFFFFF' if is_active else '#9CA3AF',
            activebackground=MODE_COLORS[m], activeforeground='#FFFFFF',
            relief='flat', bd=0, padx=10, pady=4,
            font=('Segoe UI', 9, 'bold'), cursor='hand2',
            command=lambda mo=m: _switch_mode_btn(mo)
        )
        b.pack(side='left', padx=2, pady=3)
        _dash_mode_btns[m] = b

    dash_body.pack(fill='both', expand=True, padx=0, pady=(8, 0))
    dash_sidebar.pack(side='left', fill='y')
    dash_content.pack(side='left', fill='both', expand=True, padx=(12, 16), pady=(0, 12))

    init_dash_sphere()
    tk.Label(dash_sidebar, text='Voila', bg='#16171C', fg='#FFFFFF', font=('Segoe UI', 12, 'bold')).pack(pady=(0, 16))

    nav_wrap = tk.Frame(dash_sidebar, bg='#16171C')
    nav_wrap.pack(fill='x', padx=6)

    for section, label in NAV_ITEMS:
        btn = tk.Button(
            nav_wrap, text=label, anchor='w',
            bg='#16171C', fg='#9CA3AF',
            activebackground='#252528', activeforeground='#FFFFFF',
            relief='flat', bd=0, padx=12, pady=10,
            font=('Segoe UI', 9), cursor='hand2',
            command=lambda s=section: switch_section(s),
        )
        btn.pack(fill='x', pady=2)
        nav_btn_widgets[section] = btn

    dash_canvas = tk.Canvas(dash_content, bg='#0F1115', highlightthickness=0, bd=0)
    dash_canvas.pack(fill='both', expand=True)

import urllib.request as _urllib_req
import json as _json_mod

# ─── Settings widget state ────────────────────────────────────────────────
_settings_frame_widget = None

_documents_frame_widget = None


def _make_btn(parent, text, cmd, bg='#374151', fg='#E5E7EB', width=8):
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                     activebackground='#4B5563', activeforeground='#fff',
                     relief='flat', bd=0, font=('Segoe UI', 9), cursor='hand2',
                     padx=10, pady=8, width=width)

def _api_call(method, path, payload=None):
    """Call the local voila.exe HTTP server synchronously."""
    url = f'http://localhost:8088{path}'
    try:
        if payload is not None:
            data = _json_mod.dumps(payload).encode()
            req = _urllib_req.Request(url, data=data, headers={'Content-Type': 'application/json'}, method=method)
        else:
            req = _urllib_req.Request(url, method=method)
        with _urllib_req.urlopen(req, timeout=10) as r:
            return _json_mod.loads(r.read())
    except Exception as e:
        return {'error': str(e)}


import json

def _hide_documents_widgets():
    global _documents_frame_widget
    if _documents_frame_widget:
        _documents_frame_widget.destroy()
        _documents_frame_widget = None

def _show_documents_widgets():
    global _documents_frame_widget
    _hide_documents_widgets()
    
    _documents_frame_widget = tk.Frame(dash_content, bg='#0F1115')
    _documents_frame_widget.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    
    canvas = tk.Canvas(_documents_frame_widget, bg='#0F1115', highlightthickness=0)
    scrollbar = ttk.Scrollbar(_documents_frame_widget, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg='#0F1115')
    
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        )
    )
    
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    
    inner = tk.Frame(scrollable_frame, bg='#0F1115')
    inner.pack(fill='both', expand=True, padx=4, pady=4)
    
    # Load registry
    registry_path = os.path.join(os.path.dirname(__file__), 'templates', 'registry.json')
    registry = {}
    if os.path.exists(registry_path):
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry = json.load(f)
            
    tk.Label(inner, text='Template Registry', bg='#0F1115', fg='#E5E7EB', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(10, 5))
    
    if not registry:
        tk.Label(inner, text='No templates found in registry.json.', bg='#0F1115', fg='#EF4444').pack(anchor='w')
    else:
        for tid, tdata in registry.items():
            card = tk.Frame(inner, bg='#1A1D23', bd=1, relief='solid')
            card.pack(fill='x', pady=5, padx=5)
            tk.Label(card, text=f"{tid} ({tdata.get('provider')})", bg='#1A1D23', fg='#6366F1', font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=5)
            tk.Label(card, text=f"Placeholders: {', '.join(tdata.get('placeholders', []))}", bg='#1A1D23', fg='#9CA3AF').pack(anchor='w', padx=10)
            tk.Label(card, text=f"Tags: {', '.join(tdata.get('intent_tags', []))}", bg='#1A1D23', fg='#9CA3AF').pack(anchor='w', padx=10, pady=(0, 5))
            
    # Load recent docs
    tk.Label(inner, text='Recent Documents', bg='#0F1115', fg='#E5E7EB', font=('Segoe UI', 14, 'bold')).pack(anchor='w', pady=(20, 5))
    index_path = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'documents', 'index.json')
    recent = []
    if os.path.exists(index_path):
        with open(index_path, 'r', encoding='utf-8') as f:
            recent = json.load(f)
            
    if not recent:
        tk.Label(inner, text='No recent documents.', bg='#0F1115', fg='#9CA3AF').pack(anchor='w')
    else:
        for doc in recent:
            dcard = tk.Frame(inner, bg='#1A1D23', bd=1, relief='solid')
            dcard.pack(fill='x', pady=5, padx=5)
            tk.Label(dcard, text=doc.get('title', 'Untitled'), bg='#1A1D23', fg='#10B981', font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=10, pady=5)
            tk.Label(dcard, text=f"Template: {doc.get('template_id')} | Created: {doc.get('created_at')}", bg='#1A1D23', fg='#9CA3AF').pack(anchor='w', padx=10)
            
            btn_frame = tk.Frame(dcard, bg='#1A1D23')
            btn_frame.pack(anchor='w', padx=10, pady=5)
            
            for path in doc.get('paths', []):
                def make_cmd(p=path):
                    import subprocess
                    if sys.platform == "win32": os.startfile(p)
                    elif sys.platform == "darwin": subprocess.Popen(["open", p])
                    else: subprocess.Popen(["xdg-open", p])
                tk.Button(btn_frame, text=f"Open {os.path.basename(path)}", command=make_cmd, bg='#374151', fg='#E5E7EB', relief='flat').pack(side='left', padx=(0, 5))


def _hide_settings_widgets():
    global _settings_frame_widget
    if _settings_frame_widget:
        _settings_frame_widget.destroy()
        _settings_frame_widget = None

_documents_frame_widget = None


def _show_settings_widgets():
    global _settings_frame_widget
    _hide_settings_widgets()

    # Fetch current values from agent
    data = _api_call('GET', '/api-keys')

    frame = tk.Frame(dash_content, bg='#0F1115')
    frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    _settings_frame_widget = frame

    # ─── Scrollable container ────────────────────────────────────────────────
    canvas_s = tk.Canvas(frame, bg='#0F1115', highlightthickness=0)
    scrollbar = tk.Scrollbar(frame, orient='vertical', command=canvas_s.yview)
    canvas_s.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    canvas_s.pack(side='left', fill='both', expand=True)

    inner = tk.Frame(canvas_s, bg='#0F1115')
    inner_win = canvas_s.create_window((0, 0), window=inner, anchor='nw')

    def _on_frame_configure(e):
        canvas_s.configure(scrollregion=canvas_s.bbox('all'))
    def _on_canvas_configure(e):
        canvas_s.itemconfig(inner_win, width=e.width)
    inner.bind('<Configure>', _on_frame_configure)
    canvas_s.bind('<Configure>', _on_canvas_configure)

    PAD = dict(padx=16, pady=6, sticky='w')

    # ─── Title ───────────────────────────────────────────────────────────────
    tk.Label(inner, text='⚙️  API Keys & Cloud Settings', bg='#0F1115', fg='#E5E7EB',
             font=('Segoe UI', 14, 'bold')).grid(row=0, column=0, columnspan=4, padx=16, pady=(16, 4), sticky='w')

    # ─── GROQ SECTION ────────────────────────────────────────────────────────
    groq_frame = tk.LabelFrame(inner, text=' Groq Cloud (Free tier — llama3-70b, mixtral) ',
                               bg='#1A1D23', fg='#6366F1', font=('Segoe UI', 10, 'bold'),
                               bd=1, relief='solid', labelanchor='nw')
    groq_frame.grid(row=1, column=0, columnspan=4, padx=16, pady=(12, 6), sticky='ew')

    tk.Label(groq_frame, text='API Key:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=0, column=0, padx=12, pady=8, sticky='w')

    groq_key_var = tk.StringVar()
    groq_status_var = tk.StringVar(value='● Set' if data.get('groq_api_key_set') == 'true' else '○ Not set')
    groq_status_color = '#10B981' if data.get('groq_api_key_set') == 'true' else '#6B7280'
    groq_entry = tk.Entry(groq_frame, textvariable=groq_key_var, bg='#2D3039', fg='#E5E7EB',
                          insertbackground='#E5E7EB', relief='flat', font=('Segoe UI', 9),
                          width=40, show='●')
    groq_entry.grid(row=0, column=1, padx=6, pady=8, sticky='ew')

    # Show/hide toggle
    groq_show_var = tk.BooleanVar(value=False)
    def toggle_groq_show():
        groq_entry.config(show='' if groq_show_var.get() else '●')
    tk.Checkbutton(groq_frame, text='Show', variable=groq_show_var, command=toggle_groq_show,
                   bg='#1A1D23', fg='#9CA3AF', selectcolor='#2D3039',
                   activebackground='#1A1D23', font=('Segoe UI', 8)).grid(row=0, column=2, padx=4)

    groq_status_lbl = tk.Label(groq_frame, textvariable=groq_status_var,
                                bg='#1A1D23', fg=groq_status_color, font=('Segoe UI', 9))
    groq_status_lbl.grid(row=0, column=3, padx=8, pady=8)

    tk.Label(groq_frame, text='Sec Key:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=1, column=0, padx=12, pady=4, sticky='w')
    groq_sec_key_var = tk.StringVar()
    groq_sec_entry = tk.Entry(groq_frame, textvariable=groq_sec_key_var, bg='#2D3039', fg='#E5E7EB',
                          insertbackground='#E5E7EB', relief='flat', font=('Segoe UI', 9),
                          width=40, show='●')
    groq_sec_entry.grid(row=1, column=1, padx=10, pady=8, sticky='ew')
    tk.Label(groq_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=1, column=3, sticky='w')

    # Groq Model Dropdown
    tk.Label(groq_frame, text='Model:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=2, column=0, padx=12, pady=4, sticky='w')
    
    groq_models = [
        "qwen/qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-safeguard-20b",
        "groq/compound",
        "groq/compound-mini",
        "allam-2-7b",
        "meta-llama/llama-prompt-guard-2-86m",
        "meta-llama/llama-prompt-guard-2-22m",
        "llama3-70b-8192",
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768"
    ]
    groq_model_var = tk.StringVar(value=data.get('groq_model', 'openai/gpt-oss-120b') or 'openai/gpt-oss-120b')
    
    style = ttk.Style()
    style.theme_use('default')
    style.configure('TCombobox', fieldbackground='#2D3039', background='#1A1D23', foreground='white')
    
    groq_model_cb = ttk.Combobox(groq_frame, textvariable=groq_model_var, values=groq_models, width=38, font=('Segoe UI', 9))
    groq_model_cb.grid(row=2, column=1, columnspan=2, padx=10, pady=8, sticky='w')
    tk.Label(groq_frame, text='(Free tier + tool calling)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=2, column=3, sticky='w')

    def on_groq_save():
        key = groq_key_var.get().strip()
        model = groq_model_var.get().strip()
        if not key:
            groq_status_var.set('⚠️ Enter a key first')
            groq_status_lbl.config(fg='#F59E0B')
            return
        res = _api_call('POST', '/api-keys', {'groq_api_key': key, 'groq_secondary_api_key': groq_sec_key_var.get().strip(), 'groq_model': model, 'action': 'save'})
        if 'error' in res:
            groq_status_var.set(f'⚡ {res["error"][:40]}')
            groq_status_lbl.config(fg='#EF4444')
        else:
            groq_status_var.set('✓ Saved')
            groq_status_lbl.config(fg='#10B981')
            groq_key_var.set('')

    def on_groq_verify():
        groq_status_var.set('⏳ Verifying...')
        groq_status_lbl.config(fg='#F59E0B')
        frame.update_idletasks()

        def _do():
            res = _api_call('GET', '/verify-groq')
            if res.get('status') == 'ok':
                groq_status_var.set(f'✓ OK: {res.get("response","")[:30]}')
                groq_status_lbl.config(fg='#10B981')
            else:
                groq_status_var.set(f'✗ {res.get("message", res.get("error","Unknown"))[:40]}')
                groq_status_lbl.config(fg='#EF4444')
        threading.Thread(target=_do, daemon=True).start()

    def on_groq_delete():
        res = _api_call('POST', '/api-keys', {'action': 'delete_groq'})
        if 'error' in res:
            groq_status_var.set(f'✗ {res["error"][:40]}')
            groq_status_lbl.config(fg='#EF4444')
        else:
            groq_status_var.set('○ Deleted')
            groq_status_lbl.config(fg='#6B7280')

    btn_row = tk.Frame(groq_frame, bg='#1A1D23')
    btn_row.grid(row=3, column=0, columnspan=4, padx=12, pady=(15, 15), sticky='w')
    _make_btn(btn_row, '💾 Save', on_groq_save, bg='#6366F1', width=9).pack(side='left', padx=(0, 6))
    _make_btn(btn_row, '✓ Verify', on_groq_verify, bg='#10B981', width=9).pack(side='left', padx=(0, 6))
    _make_btn(btn_row, '🗑️ Delete', on_groq_delete, bg='#DC2626', width=9).pack(side='left')

    tk.Label(groq_frame, text='Available models: qwen3.8-27b, gpt-oss-120b, compound, allam-2-7b, llama-3.1...',
             bg='#1A1D23', fg='#4B5563', font=('Segoe UI', 8, 'italic')).grid(
        row=4, column=0, columnspan=4, padx=12, pady=(15, 15), sticky='w')

    # ─── OLLAMA SECTION ──────────────────────────────────────────────────────
    ollama_frame = tk.LabelFrame(inner, text=' Ollama (Local / Ollama Cloud free tier) ',
                                 bg='#1A1D23', fg='#F59E0B', font=('Segoe UI', 10, 'bold'),
                                 bd=1, relief='solid', labelanchor='nw')
    ollama_frame.grid(row=2, column=0, columnspan=4, padx=16, pady=(12, 6), sticky='ew')

    tk.Label(ollama_frame, text='Base URL:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=0, column=0, padx=12, pady=8, sticky='w')
    ollama_url_var = tk.StringVar(value=data.get('ollama_base_url', 'http://localhost:11434'))
    tk.Entry(ollama_frame, textvariable=ollama_url_var, bg='#2D3039', fg='#E5E7EB',
             insertbackground='#E5E7EB', relief='flat', font=('Segoe UI', 9), width=42).grid(
        row=0, column=1, columnspan=3, padx=6, pady=8, sticky='ew')

    tk.Label(ollama_frame, text='Model:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=3, column=0, padx=12, pady=4, sticky='w')
    ollama_model_var = tk.StringVar(value=data.get('ollama_model', 'gemma4:31b'))
    
    ollama_models = [
        "gemma4:31b",
        "gpt-oss:120b",
        "gpt-oss:20b",
        "nemotron-3-nano:30b",
        "nemotron-3-super",
        "nemotron-3-ultra"
    ]
    ollama_model_cb = ttk.Combobox(ollama_frame, textvariable=ollama_model_var, values=ollama_models, width=40, font=('Segoe UI', 9))
    ollama_model_cb.grid(row=3, column=1, columnspan=2, padx=10, pady=8, sticky='w')
    tk.Label(ollama_frame, text='(Free tier + tool calling)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=3, column=3, sticky='w')

    tk.Label(ollama_frame, text='API Key (Opt):', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=1, column=0, padx=12, pady=4, sticky='w')
    ollama_key_var = tk.StringVar(value=data.get('ollama_api_key_set') == 'true' and '********' or '')
    tk.Entry(ollama_frame, textvariable=ollama_key_var, bg='#2D3039', fg='#E5E7EB',
             insertbackground='#E5E7EB', relief='flat', font=('Segoe UI', 9), width=42, show='*').grid(
        row=1, column=1, columnspan=3, padx=10, pady=8, sticky='ew')

    tk.Label(ollama_frame, text='Sec Key:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=2, column=0, padx=12, pady=4, sticky='w')
    ollama_sec_key_var = tk.StringVar(value=data.get('ollama_secondary_api_key_set') == 'true' and '********' or '')
    ollama_sec_entry = tk.Entry(ollama_frame, textvariable=ollama_sec_key_var, bg='#2D3039', fg='#E5E7EB',
                          insertbackground='#E5E7EB', relief='flat', font=('Segoe UI', 9), width=40, show='*')
    ollama_sec_entry.grid(row=2, column=1, padx=10, pady=8, sticky='ew')
    tk.Label(ollama_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=2, column=2, sticky='w')

    def _on_ollama_key_change(*args):
        k = ollama_key_var.get().strip()
        u = ollama_url_var.get().strip()
        if k and k != '********':
            if u == '' or u == 'http://localhost:11434':
                ollama_url_var.set('https://ollama.com')
        elif not k:
            if u == 'https://ollama.com':
                ollama_url_var.set('http://localhost:11434')
    
    ollama_key_var.trace_add('write', _on_ollama_key_change)

    ollama_status_var = tk.StringVar(value='')
    ollama_status_lbl = tk.Label(ollama_frame, textvariable=ollama_status_var,
                                  bg='#1A1D23', fg='#10B981', font=('Segoe UI', 9))
    ollama_status_lbl.grid(row=4, column=0, columnspan=4, padx=12, pady=(0, 4), sticky='w')

    def on_ollama_save():
        url = ollama_url_var.get().strip()
        model = ollama_model_var.get().strip()
        key = ollama_key_var.get().strip()
        if key == '********': key = '' # Don't resave placeholder
        if not url:
            ollama_status_var.set('⚠️ Enter Base URL first')
            ollama_status_lbl.config(fg='#F59E0B')
            return
        sec_key = ollama_sec_key_var.get().strip()
        sec_key = '' if sec_key == '********' else sec_key
        res = _api_call('POST', '/api-keys', {'ollama_base_url': url, 'ollama_model': model, 'ollama_api_key': key, 'ollama_secondary_api_key': sec_key, 'action': 'save'})
        if 'error' in res:
            ollama_status_var.set(f'⚡ {res["error"][:40]}')
            ollama_status_lbl.config(fg='#EF4444')
        else:
            ollama_status_var.set('● Saved')
            ollama_status_lbl.config(fg='#10B981')

    def on_ollama_verify():
        ollama_status_var.set('⏳ Verifying...')
        ollama_status_lbl.config(fg='#F59E0B')
        frame.update_idletasks()

        def _do():
            # Save URL/model first so the agent uses the live values
            _api_call('POST', '/api-keys', {
                'ollama_base_url': ollama_url_var.get().strip(),
                'ollama_model': ollama_model_var.get().strip(),
                'action': 'save'
            })
            res = _api_call('GET', '/verify-ollama')
            if res.get('status') == 'ok':
                ollama_status_var.set(f'✓ OK: {res.get("response","")[:30]}')
                ollama_status_lbl.config(fg='#10B981')
            else:
                ollama_status_var.set(f'✗ {res.get("message", res.get("error","Unknown"))[:50]}')
                ollama_status_lbl.config(fg='#EF4444')
        threading.Thread(target=_do, daemon=True).start()

    def on_ollama_delete():
        res = _api_call('POST', '/api-keys', {'action': 'delete_ollama'})
        if 'error' in res:
            ollama_status_var.set(f'✗ {res["error"][:40]}')
            ollama_status_lbl.config(fg='#EF4444')
        else:
            ollama_url_var.set('http://localhost:11434')
            ollama_model_var.set('llama3.2:1b')
            ollama_status_var.set('○ Cleared')
            ollama_status_lbl.config(fg='#6B7280')

    obtn_row = tk.Frame(ollama_frame, bg='#1A1D23')
    obtn_row.grid(row=5, column=0, columnspan=4, padx=12, pady=(15, 15), sticky='w')
    _make_btn(obtn_row, '💾 Save', on_ollama_save, bg='#D97706', width=9).pack(side='left', padx=(0, 6))
    _make_btn(obtn_row, '✓ Verify', on_ollama_verify, bg='#10B981', width=9).pack(side='left', padx=(0, 6))
    _make_btn(obtn_row, '🗑️ Delete', on_ollama_delete, bg='#DC2626', width=9).pack(side='left')

    tk.Label(ollama_frame, text='Ollama Cloud free models: gemma4:31b, gpt-oss:120b, nemotron-3-nano:30b, ...',
             bg='#1A1D23', fg='#4B5563', font=('Segoe UI', 8, 'italic')).grid(
        row=6, column=0, columnspan=4, padx=12, pady=(15, 15), sticky='w')

    # ─── Token Usage Section ──────────────────────────────────────────────────
    token_frame = tk.LabelFrame(inner, text=' 📊  Live Token Usage & Rate Limits ',
                                bg='#1A1D23', fg='#6366F1', font=('Segoe UI', 10, 'bold'),
                                bd=1, relief='solid', labelanchor='nw')
    token_frame.grid(row=4, column=0, columnspan=4, padx=16, pady=(12, 6), sticky='ew')

    # Status bar at top of section
    token_status_var = tk.StringVar(value='Click ↻ Refresh to fetch live data')
    tk.Label(token_frame, textvariable=token_status_var, bg='#1A1D23', fg='#6B7280',
             font=('Segoe UI', 8, 'italic')).grid(row=0, column=0, columnspan=5,
             padx=12, pady=(8, 2), sticky='w')

    # ── Groq column ────────────────────────────────────────────────────────────
    groq_col = tk.Frame(token_frame, bg='#1A1D23')
    groq_col.grid(row=1, column=0, columnspan=2, padx=12, pady=6, sticky='nsew')
    token_frame.columnconfigure(0, weight=1)
    token_frame.columnconfigure(2, weight=1)

    tk.Label(groq_col, text='⚡ Groq Cloud', bg='#1A1D23', fg='#6366F1',
             font=('Segoe UI', 10, 'bold')).pack(anchor='w')

    # Groq session stat
    groq_sess_var = tk.StringVar(value='Session: — / —')
    tk.Label(groq_col, textvariable=groq_sess_var, bg='#1A1D23', fg='#E5E7EB',
             font=('Segoe UI', 9)).pack(anchor='w', pady=(4, 0))

    # Groq daily stat
    groq_day_var = tk.StringVar(value='Today:   — / —')
    tk.Label(groq_col, textvariable=groq_day_var, bg='#1A1D23', fg='#9CA3AF',
             font=('Segoe UI', 9)).pack(anchor='w')

    # Groq rate limit stat
    groq_rl_var = tk.StringVar(value='RPM Limit: —  |  Token Limit: —')
    tk.Label(groq_col, textvariable=groq_rl_var, bg='#1A1D23', fg='#9CA3AF',
             font=('Segoe UI', 8)).pack(anchor='w', pady=(2, 4))

    # Groq progress bar (canvas)
    groq_bar_canvas = tk.Canvas(groq_col, bg='#0F1115', height=8, bd=0,
                                highlightthickness=0, relief='flat')
    groq_bar_canvas.pack(fill='x', pady=(0, 6))

    # ── Separator ─────────────────────────────────────────────────────────────
    tk.Frame(token_frame, bg='#2A2D35', width=1).grid(row=1, column=2, sticky='ns', padx=8)

    # ── Ollama column ──────────────────────────────────────────────────────────
    ollama_col = tk.Frame(token_frame, bg='#1A1D23')
    ollama_col.grid(row=1, column=3, columnspan=2, padx=12, pady=6, sticky='nsew')

    tk.Label(ollama_col, text='🦙 Ollama Cloud', bg='#1A1D23', fg='#F59E0B',
             font=('Segoe UI', 10, 'bold')).pack(anchor='w')

    ollama_sess_var = tk.StringVar(value='Session: — / —')
    tk.Label(ollama_col, textvariable=ollama_sess_var, bg='#1A1D23', fg='#E5E7EB',
             font=('Segoe UI', 9)).pack(anchor='w', pady=(4, 0))

    ollama_day_var = tk.StringVar(value='Today:   — / —')
    tk.Label(ollama_col, textvariable=ollama_day_var, bg='#1A1D23', fg='#9CA3AF',
             font=('Segoe UI', 9)).pack(anchor='w')

    tk.Label(ollama_col, text='Per-request tracking (no public billing API)',
             bg='#1A1D23', fg='#4B5563', font=('Segoe UI', 8, 'italic')).pack(anchor='w', pady=(2, 4))

    ollama_bar_canvas = tk.Canvas(ollama_col, bg='#0F1115', height=8, bd=0,
                                  highlightthickness=0, relief='flat')
    ollama_bar_canvas.pack(fill='x', pady=(0, 6))

    def _draw_progress_bar(canvas_widget, used, total, color='#6366F1'):
        """Draw a sleek progress bar on a tk.Canvas."""
        canvas_widget.update_idletasks()
        w = max(canvas_widget.winfo_width(), 200)
        canvas_widget.delete('all')
        # Background track
        canvas_widget.create_rectangle(0, 2, w, 6, fill='#2A2D35', outline='')
        # Fill
        if total > 0:
            fill_w = max(4, int((used / total) * w))
            fill_w = min(fill_w, w)
            pct = used / total
            # Color gradient: green → yellow → red
            if pct < 0.5:
                c = color
            elif pct < 0.8:
                c = '#F59E0B'
            else:
                c = '#EF4444'
            canvas_widget.create_rectangle(0, 2, fill_w, 6, fill=c, outline='')
        else:
            # Unknown total — show pulsing unknown bar
            canvas_widget.create_rectangle(0, 2, w // 3, 6, fill='#374151', outline='')

    def _fmt_tokens(n):
        if n >= 1_000_000:
            return f'{n/1_000_000:.1f}M'
        elif n >= 1_000:
            return f'{n/1_000:.1f}k'
        return str(n)

    def _load_token_data(fetch_limits=False):
        """Fetch token usage from the agent endpoint (runs in background thread)."""
        try:
            path = '/token-usage?fetch_limits=1' if fetch_limits else '/token-usage'
            data = _api_call('GET', path)
            if 'error' in data:
                token_status_var.set(f'⚠ {data["error"][:60]}')
                return

            # ── Groq ────────────────────────────────────────────────────────
            g_s_in  = data.get('groq_session_in', 0)
            g_s_out = data.get('groq_session_out', 0)
            g_d_in  = data.get('groq_day_in', 0)
            g_d_out = data.get('groq_day_out', 0)
            g_sess = g_s_in + g_s_out
            g_day  = g_d_in + g_d_out

            g_tpd_limit = data.get('groq_tpd_limit', 0)
            g_tpd_rem   = data.get('groq_tpd_remaining', 0)
            g_rpm_limit = data.get('groq_rpm_limit', 0)
            g_rpm_rem   = data.get('groq_rpm_remaining', 0)

            sess_txt = f'Session:  {_fmt_tokens(g_sess)} ({_fmt_tokens(g_s_in)} in / {_fmt_tokens(g_s_out)} out)'
            day_txt  = f'Today:    {_fmt_tokens(g_day)}  ({_fmt_tokens(g_d_in)} in / {_fmt_tokens(g_d_out)} out)'
            groq_sess_var.set(sess_txt)
            groq_day_var.set(day_txt)

            if g_tpd_limit > 0:
                g_used = g_tpd_limit - g_tpd_rem
                rl_txt = f'RPM: {g_rpm_rem}/{g_rpm_limit}  |  TPM limit: {_fmt_tokens(g_tpd_limit)}  remaining: {_fmt_tokens(g_tpd_rem)}'
                groq_rl_var.set(rl_txt)
                _draw_progress_bar(groq_bar_canvas, g_used, g_tpd_limit, '#6366F1')
            else:
                groq_rl_var.set('Rate limits: click ↻ Refresh (fetches live headers from Groq)')
                _draw_progress_bar(groq_bar_canvas, g_day, 0, '#6366F1')

            # ── Ollama ──────────────────────────────────────────────────────
            o_s_in  = data.get('ollama_session_in', 0)
            o_s_out = data.get('ollama_session_out', 0)
            o_d_in  = data.get('ollama_day_in', 0)
            o_d_out = data.get('ollama_day_out', 0)
            o_sess = o_s_in + o_s_out
            o_day  = o_d_in + o_d_out

            o_sess_txt = f'Session:  {_fmt_tokens(o_sess)} ({_fmt_tokens(o_s_in)} in / {_fmt_tokens(o_s_out)} out)'
            o_day_txt  = f'Today:    {_fmt_tokens(o_day)}  ({_fmt_tokens(o_d_in)} in / {_fmt_tokens(o_d_out)} out)'
            ollama_sess_var.set(o_sess_txt)
            ollama_day_var.set(o_day_txt)
            _draw_progress_bar(ollama_bar_canvas, o_day, 0, '#F59E0B')

            reset = data.get('reset_date', '')
            token_status_var.set(f'✓ Updated  |  Daily counters reset: {reset}  |  Last refresh: {time.strftime("%H:%M:%S")}')

        except Exception as e:
            token_status_var.set(f'⚠ Error: {str(e)[:60]}')

    def _on_refresh(fetch_limits=False):
        token_status_var.set('⏳ Fetching...')
        token_frame.update_idletasks()
        threading.Thread(target=_load_token_data, args=(fetch_limits,), daemon=True).start()

    # Buttons row
    btn_token_row = tk.Frame(token_frame, bg='#1A1D23')
    btn_token_row.grid(row=2, column=0, columnspan=5, padx=12, pady=(4, 12), sticky='w')
    tk.Button(btn_token_row, text='↻ Refresh', command=lambda: _on_refresh(False),
              bg='#374151', fg='#E5E7EB', font=('Segoe UI', 9), relief='flat',
              padx=10, pady=5, cursor='hand2').pack(side='left', padx=(0, 6))
    tk.Button(btn_token_row, text='⚡ Fetch Rate Limits (Groq)',
              command=lambda: _on_refresh(True),
              bg='#4338CA', fg='#E5E7EB', font=('Segoe UI', 9), relief='flat',
              padx=10, pady=5, cursor='hand2').pack(side='left', padx=(0, 6))
    tk.Label(btn_token_row, text='Rate limits call Groq API — avoid hammering',
             bg='#1A1D23', fg='#4B5563', font=('Segoe UI', 8, 'italic')).pack(side='left', padx=8)

    # Auto-load on settings page open (no rate limit fetch, just local data)
    threading.Thread(target=_load_token_data, args=(False,), daemon=True).start()

    # ─── Info footer ─────────────────────────────────────────────────────────

    # --- FLUSH MEMORY ---
    def flush_memory():
        try:
            _api_call('POST', '/flush_memory', {})
            tk.messagebox.showinfo("Memory Flushed", "Command memory has been successfully cleared.")
        except Exception as e:
            tk.messagebox.showerror("Error", str(e))
            
    mem_frame = tk.Frame(inner, bg='#1A1D23', highlightbackground='#2A2D35', highlightthickness=1)
    mem_frame.grid(row=8, column=0, columnspan=4, sticky='ew', padx=16, pady=12)
    tk.Label(mem_frame, text='Command Memory Database', bg='#1A1D23', fg='#E5E7EB', font=('Segoe UI', 11, 'bold')).pack(side='left', padx=12, pady=12)
    tk.Button(mem_frame, text='Flush Data', command=flush_memory, bg='#EF4444', fg='white', font=('Segoe UI', 9, 'bold'), relief='flat', padx=10, pady=2, cursor='hand2').pack(side='right', padx=12, pady=12)
    
    info = tk.Frame(inner, bg='#0F1115')
    info.grid(row=3, column=0, columnspan=4, padx=16, pady=12, sticky='ew')
    tk.Label(info, text='Version: 1.0.0  |  Platform: Windows  |  Build: Stable',
             bg='#0F1115', fg='#374151', font=('Segoe UI', 9)).pack(anchor='w')

def refresh_dashboard_content():

    global dash_canvas, simulated_dash_time
    if mobile_clients > 0:
        simulated_dash_time += 0.2
    if not dashboard_active or dash_canvas is None:
        return

    # Always destroy settings widget frame when refreshing (navigated away)
    if current_section != 'Settings':
        _hide_settings_widgets()
    if current_section != 'Documents':
        _hide_documents_widgets()

    build_dashboard_ui()
    dash_title_var.set(current_section)
    session_duration = int((time.time() - usage_stats['session_start']) / 60)
    dash_session_var.set(f'{session_duration}m')
    for section, _ in NAV_ITEMS:
        _style_nav_button(section)

    dash_canvas.delete('all')
    w = max(dash_canvas.winfo_width(), 700)
    h = max(dash_canvas.winfo_height(), 480)

    if current_section == 'Dashboard':
        _draw_dashboard_section(dash_canvas, w, h)
    elif current_section == 'Connections':
        _draw_connections_section(dash_canvas, w, h)
    elif current_section == 'Analytics':
        _draw_analytics_section(dash_canvas, w, h)
    elif current_section == 'Settings':
        _show_settings_widgets()
        return
    elif current_section == 'Documents':
        _show_documents_widgets()
        return  # Settings are all widgets, not canvas drawing
    elif current_section == 'Teams':
        _draw_teams_section(dash_canvas, w, h)
    else:
        dash_canvas.create_text(w // 2, h // 2 - 12, text=current_section, fill='#E5E7EB', font=('Segoe UI', 16, 'bold'))
        dash_canvas.create_text(w // 2, h // 2 + 16, text='Coming soon', fill='#6B7280', font=('Segoe UI', 11))

def _draw_connections_section(dc, w, h):
    mobile_status = 'Connected' if mobile_clients > 0 else 'Offline'
    mobile_color = '#10B981' if mobile_clients > 0 else '#6B7280'
    dc.create_rectangle(10, 20, w - 10, 110, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(24, 42, text='Mobile Clients', fill='#888888', font=('Segoe UI', 9), anchor='w')
    dc.create_text(24, 72, text=mobile_status, fill=mobile_color, font=('Segoe UI', 20, 'bold'), anchor='w')
    dc.create_text(w - 24, 72, text=str(mobile_clients), fill='#6B7280', font=('Segoe UI', 12), anchor='e')
    dc.create_rectangle(10, 126, w - 10, 216, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(24, 148, text='Backend Relay', fill='#888888', font=('Segoe UI', 9), anchor='w')
    backend_color = '#10B981' if backend_status == 'Active' else '#EF4444'
    dc.create_text(24, 178, text=backend_status, fill=backend_color, font=('Segoe UI', 20, 'bold'), anchor='w')
    dc.create_text(w - 24, 178, text=f"{usage_stats['avg_latency_ms']}ms", fill='#6B7280', font=('Segoe UI', 12), anchor='e')

    # Cloud AI Mode
    dc.create_rectangle(10, 232, w - 10, 322, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(24, 254, text='Execution Mode', fill='#888888', font=('Segoe UI', 9), anchor='w')
    dc.create_text(24, 284, text=current_mode, fill=MODE_COLORS[current_mode], font=('Segoe UI', 20, 'bold'), anchor='w')
    dc.create_text(w - 24, 284, text='Toggle on main widget', fill='#6B7280', font=('Segoe UI', 10), anchor='e')

def _draw_analytics_section(dc, w, h):
    success_rate = 0
    if usage_stats['commands_executed'] > 0:
        success_rate = int((usage_stats['commands_successful'] / usage_stats['commands_executed']) * 100)
    session_duration = int((time.time() - usage_stats['session_start']) / 60)
    commands_per_min = int(usage_stats['commands_executed'] / max(0.1, (time.time() - usage_stats['session_start']) / 60.0))

    # Stats cards row
    card_w = (w - 35) // 3
    card_h = 80
    card_y = 20

    # Commands Executed
    dc.create_rectangle(10, card_y, card_w, card_y + card_h, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(24, card_y + 20, text='Commands Executed', fill='#888888', font=('Segoe UI', 8), anchor='w')
    dc.create_text(24, card_y + 50, text=str(usage_stats['commands_executed']), fill='#E5E7EB', font=('Segoe UI', 24, 'bold'), anchor='w')

    # Success Rate
    dc.create_rectangle(card_w + 15, card_y, card_w * 2 + 15, card_y + card_h, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(card_w + 27, card_y + 20, text='Success Rate', fill='#888888', font=('Segoe UI', 8), anchor='w')
    dc.create_text(card_w + 27, card_y + 50, text=f"{success_rate}%", fill='#10B981', font=('Segoe UI', 24, 'bold'), anchor='w')

    # Avg Latency
    dc.create_rectangle(card_w * 2 + 30, card_y, w - 10, card_y + card_h, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(card_w * 2 + 42, card_y + 20, text='Avg Latency', fill='#888888', font=('Segoe UI', 8), anchor='w')
    dc.create_text(card_w * 2 + 42, card_y + 50, text=f"{usage_stats['avg_latency_ms']}ms", fill='#E5E7EB', font=('Segoe UI', 24, 'bold'), anchor='w')

    # Performance timeline
    timeline_y = card_y + card_h + 20
    dc.create_text(10, timeline_y, text='Performance Timeline', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    
    timeline_h = 150
    dc.create_rectangle(10, timeline_y + 20, w - 10, timeline_y + 20 + timeline_h, fill='#1A1D23', outline='#2A2D35')
    
    # Draw timeline bars from actual data
    timeline_data = usage_stats.get('timeline_data', [])
    if not timeline_data:
        timeline_data = [0] * 20
    
    bar_count = min(len(timeline_data), 20)
    bar_w = (w - 40) // 20
    
    # Scale: max expected latency around 5000ms
    max_expected_ms = 5000.0
    
    for i in range(bar_count):
        if i < len(timeline_data):
            # Scale milliseconds to pixels (max height = timeline_h - 20)
            ms = timeline_data[i]
            scaled_height = (ms / max_expected_ms) * (timeline_h - 20)
            height = min(timeline_h - 20, max(4, scaled_height))
            
            # Color logic: Low latency (< 1500) = Green, Med (< 3000) = Orange, High = Red
            if ms < 1500:
                color = '#10B981' # Green
            elif ms < 3000:
                color = '#F59E0B' # Orange
            else:
                color = '#EF4444' # Red
                
            x = 20 + i * bar_w
            y = timeline_y + 20 + timeline_h - height
            dc.create_rectangle(x, y, x + bar_w - 2, timeline_y + 20 + timeline_h, fill=color, outline='')

    # Detailed stats
    stats_y = timeline_y + 20 + timeline_h + 20
    dc.create_text(10, stats_y, text='Detailed Statistics', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    
    dc.create_rectangle(10, stats_y + 20, w - 10, stats_y + 120, fill='#1A1D23', outline='#2A2D35')
    
    dc.create_text(24, stats_y + 40, text=f"Successful: {usage_stats['commands_successful']}", fill='#10B981', font=('Segoe UI', 11), anchor='w')
    dc.create_text(24, stats_y + 65, text=f"Failed: {usage_stats['commands_failed']}", fill='#EF4444', font=('Segoe UI', 11), anchor='w')
    dc.create_text(24, stats_y + 90, text=f"Commands/min: {commands_per_min}", fill='#6B7280', font=('Segoe UI', 11), anchor='w')
    dc.create_text(w - 24, stats_y + 40, text=f"Session: {session_duration}m", fill='#6B7280', font=('Segoe UI', 11), anchor='e')
    dc.create_text(w - 24, stats_y + 65, text=f"Peak/min: {usage_stats['peak_commands_per_min']}", fill='#6B7280', font=('Segoe UI', 11), anchor='e')

def _draw_settings_section(dc, w, h):
    """Settings section is rendered as real Tk widgets inside the dashboard canvas frame.
    We use a dedicated frame overlaid on the canvas area for proper Entry/Button support."""
    # This is called when we just need a placeholder while the real widget frame loads.
    dc.create_text(w // 2, 40, text='API Keys & Settings', fill='#E5E7EB', font=('Segoe UI', 14, 'bold'))
    dc.create_text(w // 2, 70, text='Loading...', fill='#6B7280', font=('Segoe UI', 10))

def _draw_dashboard_section(dc, w, h):
    card_w = (w - 35) // 2
    card_h = 70
    mobile_status = 'Connected' if mobile_clients > 0 else 'Offline'
    mobile_color = '#10B981' if mobile_clients > 0 else '#6B7280'

    dc.create_rectangle(0, 10, card_w, 10 + card_h, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(12, 28, text='Mobile', fill='#888888', font=('Segoe UI', 8), anchor='w')
    dc.create_text(12, 52, text=mobile_status, fill=mobile_color, font=('Segoe UI', 16, 'bold'), anchor='w')
    dc.create_text(card_w - 12, 52, text=str(mobile_clients), fill='#6B7280', font=('Segoe UI', 11), anchor='e')

    dc.create_rectangle(card_w + 15, 10, card_w * 2 + 15, 10 + card_h, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(card_w + 27, 28, text='Backend', fill='#888888', font=('Segoe UI', 8), anchor='w')
    backend_color = '#10B981' if backend_status == 'Active' else '#EF4444'
    dc.create_text(card_w + 27, 52, text=backend_status, fill=backend_color, font=('Segoe UI', 16, 'bold'), anchor='w')
    dc.create_text(card_w * 2 + 3, 52, text=f"{usage_stats['avg_latency_ms']}ms", fill='#6B7280', font=('Segoe UI', 10), anchor='e')

    success_rate = 0
    if usage_stats['commands_executed'] > 0:
        success_rate = int((usage_stats['commands_successful'] / usage_stats['commands_executed']) * 100)
    session_duration = int((time.time() - usage_stats['session_start']) / 60)
    commands_per_min = int(usage_stats['commands_executed'] / max(0.1, (time.time() - usage_stats['session_start']) / 60.0))

    radar_y = 100
    radar_size = min(160, w // 2 - 30)
    radar_cx = radar_size // 2 + 20
    radar_cy = radar_y + radar_size // 2
    radar_r = max(30, radar_size // 2 - 16)

    dc.create_text(0, radar_y, text='Performance Radar', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    t_val = simulated_dash_time
    val_stability = 0.75 + math.sin(t_val) * 0.15
    val_reliability = 0.8 + math.cos(t_val * 0.7) * 0.1
    val_quality = 0.85 + math.sin(t_val * 1.3) * 0.1
    
    axis_values = [
        max(0.1, success_rate / 100.0),
        max(0.1, min(1.0, commands_per_min / 10.0 + math.sin(t_val*0.5)*0.1)),
        val_stability, 
        val_reliability,
        max(0.1, 1.0 - (usage_stats['avg_latency_ms'] / 5000.0) + math.cos(t_val)*0.05),
        val_quality,
    ]
    num_axes = 6
    labels = ['Success', 'Speed', 'Stability', 'Reliability', 'Efficiency', 'Quality']

    for level in range(1, 4):
        lr = radar_r * level / 4
        pts = []
        for i in range(num_axes):
            ang = math.pi / 2 - (2 * math.pi * i / num_axes)
            pts.extend([radar_cx + lr * math.cos(ang), radar_cy - lr * math.sin(ang)])
        dc.create_polygon(pts, outline='#2A2D35', fill='')

    data_pts = []
    for i in range(num_axes):
        ang = math.pi / 2 - (2 * math.pi * i / num_axes)
        val = axis_values[i]
        data_pts.extend([radar_cx + radar_r * val * math.cos(ang), radar_cy - radar_r * val * math.sin(ang)])
        lx = radar_cx + (radar_r + 14) * math.cos(ang)
        ly = radar_cy - (radar_r + 14) * math.sin(ang)
        dc.create_text(lx, ly, text=labels[i], fill='#6B7280', font=('Segoe UI', 7))

    if len(data_pts) >= 6:
        dc.create_polygon(data_pts, outline='#6366F1', fill='#6366F1', stipple='gray50', width=2)

    heatmap_y = radar_y + radar_size + 24
    dc.create_text(0, heatmap_y, text='Activity Heatmap', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    heatmap_data = ensure_heatmap_cache()
    cell_w = max(24, w // 7)
    cell_h = 16
    colors = ['#1A1D23', '#1E3A5F', '#2563EB', '#3B82F6', '#60A5FA']
    for day in range(7):
        for hour in range(5):
            intensity = heatmap_data[day][hour]
            idx = min(4, int(intensity * 5))
            dc.create_rectangle(day * cell_w, heatmap_y + 18 + hour * cell_h, day * cell_w + cell_w - 3, heatmap_y + 18 + hour * cell_h + cell_h - 2, fill=colors[idx], outline='')

dash_transition_progress = 0.0
is_dash_transitioning = False
dash_opening = False

def open_dashboard():
    global dashboard_active, heatmap_cache, is_dash_transitioning, dash_opening, dash_transition_progress
    if is_dash_transitioning: return
    build_dashboard_ui()
    heatmap_cache = None
    dashboard_active = True
    
    # Hide all canvas items EXCEPT the background pill
    for item in face_parts + (status_text, title_text, mode_badge_bg, mode_badge_text, close_btn_bg, close_btn):
        try: canvas.itemconfig(item, state='hidden')
        except: pass
        
    # We do NOT pack dashboard_frame yet! We let the empty canvas animate to prevent layout lag.
    is_dash_transitioning = True
    dash_opening = True
    dash_transition_progress = 0.0
    animate_dashboard_size()

def close_dashboard():
    global dashboard_active, heatmap_cache, is_dash_transitioning, dash_opening, dash_transition_progress
    if is_dash_transitioning: return
    dashboard_active = False
    heatmap_cache = None
    
    # Instantly hide heavy UI to prevent lag, restore empty canvas for the animation
    dashboard_frame.pack_forget()
    canvas.pack(fill='both', expand=True)
    
    is_dash_transitioning = True
    dash_opening = False
    dash_transition_progress = 1.0
    animate_dashboard_size()

def animate_dashboard_size():
    global is_dash_transitioning, dash_transition_progress, current_width, current_height
    if not is_dash_transitioning: return
        
    speed = 0.08 # ~12 frames
    if dash_opening:
        dash_transition_progress += speed
        if dash_transition_progress >= 1.0:
            dash_transition_progress = 1.0
            is_dash_transitioning = False
    else:
        dash_transition_progress -= speed
        if dash_transition_progress <= 0.0:
            dash_transition_progress = 0.0
            is_dash_transitioning = False
            
    # Cubic ease-out
    t = dash_transition_progress
    ease = 1 - (1 - t) * (1 - t) * (1 - t)
    
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    target_x = (screen_w - DASHBOARD_W) // 2
    target_y = (screen_h - DASHBOARD_H) // 2
    
    start_x, start_y = original_pos
    start_w, start_h = 240, 65
    
    w = int(start_w + (DASHBOARD_W - start_w) * ease)
    h = int(start_h + (DASHBOARD_H - start_h) * ease)
    x = int(start_x + (target_x - start_x) * ease)
    y = int(start_y + (target_y - start_y) * ease)
    
    root.geometry(f'{w}x{h}+{x}+{y}')
    current_width = w
    current_height = h
    
    # Hardware-accelerated canvas morph (no layout engine lag!)
    morph_r = int(27 + (10 - 27) * ease)
    # Interpolate padding so the pill seamlessly connects with the idle state (padding 5)
    pad = int(5 + (0 - 5) * ease)
    set_round_rect(pill, pad, pad, w - pad, h - pad, morph_r)
    canvas.itemconfig(pill, fill='#0F1115', outline='#27272a') # blend into dashboard color
    canvas.config(width=w, height=h)
    
    # Critical for smooth Tkinter resizing: force the layout engine to paint the canvas 
    # immediately, synchronizing it with the OS-level root.geometry() window resize!
    root.update_idletasks()
    
    if not is_dash_transitioning:
        if dash_opening:
            canvas.pack_forget()
            dashboard_frame.pack(fill='both', expand=True)
            refresh_dashboard_content()
        else:
            restore_mini_popup_elements(start_w, start_h)
            
    if is_dash_transitioning:
        root.after(16, animate_dashboard_size)

def ensure_heatmap_cache():
    global heatmap_cache
    # Animate smoothly without full random flicker
    cache = []
    t = simulated_dash_time
    for d in range(7):
        row = []
        for h in range(5):
            # Slow moving wave pattern for a "live data" feel
            v1 = math.sin(t * 0.5 + d * 0.8) 
            v2 = math.cos(t * 0.3 + h * 1.2)
            intensity = (v1 + v2) * 0.25 + 0.5
            
            # Boost intensity slightly based on real usage
            if mobile_clients > 0:
                intensity += 0.2
            if usage_stats['commands_executed'] > 0:
                intensity += 0.1
                
            intensity = max(0.0, min(1.0, intensity))
            row.append(intensity)
        cache.append(row)
    return cache

def toggle_dashboard():
    """Smooth animated switch between mini popup canvas and dashboard frame."""
    global original_pos, original_size
    if not dashboard_active:
        original_pos = (root.winfo_x(), root.winfo_y())
        original_size = (240, 65)
        open_dashboard()
    else:
        close_dashboard()

def update_size():
    """Handle size changes (keep for compatibility with existing code)"""
    if dashboard_active:
        return
    if current_width != target_width or current_height != target_height:
        if not transition_in_progress:
            transition_in_progress = True
            transition_progress = 0.0
            animate_size_transition()

def animate_size_transition():
    """Internal function for smooth size animation"""
    global current_width, current_height, target_width, target_height, transition_progress, sx, sy, cx, cy, transition_in_progress
    
    # Increment transition progress
    transition_progress += 0.05  # Slower, smoother transition
    if transition_progress > 1.0:
        transition_progress = 1.0
    
    # Easing function (ease-out cubic)
    ease = 1 - pow(1 - transition_progress, 3)
    
    # Interpolate between current and target
    new_width = int(current_width + (target_width - current_width) * ease)
    new_height = int(current_height + (target_height - current_height) * ease)
    
    # Update window geometry
    current_x = root.winfo_x()
    current_y = root.winfo_y()
    root.geometry(f"{new_width}x{new_height}+{current_x}+{current_y}")
    
    # Update canvas size
    canvas.config(width=new_width, height=new_height)
    
    # Reposition elements based on new width
    new_close_x = new_width - 25
    
    # Update status text width
    canvas.itemconfig(status_text, width=max(150, new_width - 120))
    
    # Update close button position
    canvas.coords(close_btn, new_close_x, 45)
    canvas.coords(close_btn_bg, new_close_x - 10, 35, new_close_x + 10, 55)
    
    # Update pill outline to match new width and morph radius
    if target_width > 240:
        new_r = int(27 + (15 - 27) * ease)
    else:
        new_r = int(15 + (27 - 15) * ease)
    set_round_rect(pill, 5, 5, new_width - 5, new_height - 5, new_r)
    
    # Update current values
    current_width = new_width
    current_height = new_height
    
    # Continue transition if not complete
    if transition_progress < 1.0:
        root.after(16, animate_size_transition)  # ~60fps
    else:
        # Reset progress for next transition
        transition_progress = 0.0
        transition_in_progress = False

def animation_loop():
    global anim_frame, usage_stats, current_rendered_state, transition_scale, transitioning
    anim_frame += 1
    dots = "." * ((anim_frame // 10) % 4)

    # --- COMPUTE ANIMATION MATH UNCONDITIONALLY (OUTSIDE OF DASHBOARD CHECKS) ---
    pulse = math.sin(anim_frame * 0.03) * 1.0
    t = anim_frame * 0.01
    
    r1_x = t * 1.5 + math.sin(t * 0.8) * 1.2
    r1_y = t * 0.9 + math.cos(t * 1.1) * 1.5
    r1_z = t * 2.1 + math.sin(t * 0.5) * 0.8

    r2_x = -t * 0.8 + math.cos(t * 0.6) * 2.0
    r2_y = t * 1.2 + math.sin(t * 0.4) * 1.8
    r2_z = -t * 1.5 + math.cos(t * 0.7) * 1.2

    r3_x = t * 0.5 + math.sin(t * 0.3) * 2.5
    r3_y = -t * 0.7 + math.cos(t * 0.25) * 3.0
    r3_z = t * 0.4 + math.sin(t * 0.2) * 2.0
    
    # ALWAYS UPDATE DASHBOARD SPHERE (it's independent of dashboard_active flag)
    # The user explicitly wants it to ALWAYS spin now to avoid any freeze bugs
    update_dash_sphere(pulse, r1_x, r1_y, r1_z, r2_x, r2_y, r2_z, r3_x, r3_y, r3_z)

    if not dashboard_active and not dashboard_transition_in_progress:
        if alert_state.get("state_changed"):
            update_expression()
            alert_state["state_changed"] = False

        # State transition morphing logic
        if current_rendered_state != ai_state and not transitioning:
            transitioning = True
            
        if transitioning:
            transition_scale -= 0.15
            if transition_scale <= 0:
                transition_scale = 0
                current_rendered_state = ai_state
                transitioning = False
        else:
            if transition_scale < 1.0:
                transition_scale += 0.15
                if transition_scale > 1.0:
                    transition_scale = 1.0

        if mobile_clients == 0:
            if not alert_state["active"]:
                canvas.itemconfig(status_text, text="Offline (Standing by)", fill='#6b7280')
            canvas.itemconfig(core_bg, fill='#18181b')
            target_outline = '#6666ff' if is_hovering_pill else '#27272a'
            canvas.itemconfig(pill, outline=target_outline, fill='#09090b')
            canvas.itemconfig(sun_aura, state="hidden")
            canvas.itemconfig(sun_glow4, state="hidden")
            canvas.itemconfig(sun_glow3, state="hidden")
            canvas.itemconfig(sun_glow2, state="hidden")
            canvas.itemconfig(sun_glow1, state="hidden")
            canvas.itemconfig(core_bg, state="hidden")
            canvas.itemconfig(shadow1, state="hidden")
            canvas.itemconfig(shadow2, state="hidden")
            canvas.itemconfig(shadow3, state="hidden")
            canvas.itemconfig(core_arc1, state="hidden")
            canvas.itemconfig(core_arc2, state="hidden")
            canvas.itemconfig(core_arc3, state="hidden")
            canvas.itemconfig(term_prompt, state="hidden")
            canvas.itemconfig(file_icon, state="hidden")
            canvas.itemconfig(radar_arc, state="hidden")
            canvas.itemconfig(browser_box, state="hidden")
            canvas.itemconfig(browser_line, state="hidden")
            canvas.itemconfig(mode_badge_bg, fill='#1f2937')
            canvas.itemconfig(mode_badge_text, fill='#4b5563', text=current_mode)

        else:
            canvas.itemconfig(pill, fill='#18181b')
            canvas.itemconfig(status_text, state='normal')
            canvas.itemconfig(mode_badge_bg, fill='#27272a')
            canvas.itemconfig(mode_badge_text, fill='#9ca3af', text=current_mode)
            
            visual_state = current_rendered_state
            scale = transition_scale
            
            r1 = 16 * scale
            r2 = 12 * scale
            r3 = 20 * scale
            rr = 18 * scale
            
            # Massive sun aura (increased star size)
            canvas.coords(sun_aura, cx-(26+pulse*1.2)*scale, cy-(26+pulse*1.2)*scale, cx+(26+pulse*1.2)*scale, cy+(26+pulse*1.2)*scale)
            canvas.coords(sun_glow4, cx-(22+pulse*1.0)*scale, cy-(22+pulse*1.0)*scale, cx+(22+pulse*1.0)*scale, cy+(22+pulse*1.0)*scale)
            canvas.coords(sun_glow3, cx-(18+pulse*0.8)*scale, cy-(18+pulse*0.8)*scale, cx+(18+pulse*0.8)*scale, cy+(18+pulse*0.8)*scale)
            canvas.coords(sun_glow2, cx-(14+pulse*0.6)*scale, cy-(14+pulse*0.6)*scale, cx+(14+pulse*0.6)*scale, cy+(14+pulse*0.6)*scale)
            canvas.coords(sun_glow1, cx-(10+pulse*0.3)*scale, cy-(10+pulse*0.3)*scale, cx+(10+pulse*0.3)*scale, cy+(10+pulse*0.3)*scale)
            canvas.coords(core_bg, cx-(6)*scale, cy-(6)*scale, cx+(6)*scale, cy+(6)*scale)

            update_3d_ring(canvas, core_arc1, cx, cy, 14, r1_x, r1_y, r1_z, scale, shadow1, 2*scale)
            update_3d_ring(canvas, core_arc2, cx, cy, 17, r2_x, r2_y, r2_z, scale, shadow2, 2*scale)
            update_3d_ring(canvas, core_arc3, cx, cy, 20, r3_x, r3_y, r3_z, scale, shadow3, 2*scale)
            canvas.coords(radar_arc, cx-rr, cy-rr, cx+rr, cy+rr)
            
            canvas.itemconfig(sun_aura, state="normal")
            canvas.itemconfig(sun_glow4, state="normal")
            canvas.itemconfig(sun_glow3, state="normal")
            canvas.itemconfig(sun_glow2, state="normal")
            canvas.itemconfig(sun_glow1, state="normal")
            canvas.itemconfig(core_bg, state="normal")
            canvas.itemconfig(shadow1, state="normal")
            canvas.itemconfig(shadow2, state="normal")
            canvas.itemconfig(shadow3, state="normal")
            canvas.itemconfig(core_arc1, state="normal")
            canvas.itemconfig(core_arc2, state="normal")
            canvas.itemconfig(core_arc3, state="normal")
            canvas.itemconfig(term_prompt, state="hidden")
            canvas.itemconfig(file_icon, state="hidden")
            canvas.itemconfig(radar_arc, state="hidden")
            canvas.itemconfig(browser_box, state="hidden")
            canvas.itemconfig(browser_line, state="hidden")

            target_text = "Standing by"
            target_color = '#9ca3af'
            target_outline = '#27272a'
            show_dots = False

            if visual_state == "THINKING":
                target_text = "Thinking"
                target_color = '#fbbf24'
                target_outline = '#b45309'
                show_dots = True
                canvas.itemconfig(sun_aura, fill='#451a03')
                canvas.itemconfig(sun_glow4, fill='#78350f')
                canvas.itemconfig(sun_glow3, fill='#b45309')
                canvas.itemconfig(sun_glow2, fill='#d97706')
                canvas.itemconfig(sun_glow1, fill='#f59e0b')
                canvas.itemconfig(core_bg, fill='#fef3c7')
                canvas.itemconfig(core_arc1, fill='#fcd34d')
                canvas.itemconfig(core_arc2, fill='#fbbf24')
                canvas.itemconfig(core_arc3, fill='#f59e0b')
            elif visual_state == "SEARCH":
                target_text = "Searching"
                target_color = '#38bdf8'
                target_outline = '#0284c7'
                show_dots = True
                canvas.itemconfig(sun_glow3, state="hidden")
                canvas.itemconfig(sun_glow2, state="hidden")
                canvas.itemconfig(sun_glow1, state="hidden")
                canvas.itemconfig(core_bg, state="hidden")
                canvas.itemconfig(core_arc1, state="hidden")
                canvas.itemconfig(core_arc2, state="hidden")
                canvas.itemconfig(core_arc3, state="hidden")
                if scale > 0.5:
                    canvas.itemconfig(radar_arc, state="normal")
                # Spin radar
                canvas.itemconfig(radar_arc, start=(anim_frame * -8) % 360)
            elif visual_state == "BROWSE":
                target_text = "Browsing"
                target_color = '#f97316'
                target_outline = '#c2410c'
                show_dots = True
                canvas.itemconfig(sun_glow3, state="hidden")
                canvas.itemconfig(sun_glow2, state="hidden")
                canvas.itemconfig(sun_glow1, state="hidden")
                canvas.itemconfig(core_bg, state="hidden")
                canvas.itemconfig(core_arc1, state="hidden")
                canvas.itemconfig(core_arc2, state="hidden")
                canvas.itemconfig(core_arc3, state="hidden")
                if scale > 0.5:
                    canvas.itemconfig(browser_box, state="normal")
                    canvas.itemconfig(browser_line, state="normal")
                bounce = math.sin(anim_frame * 0.15) * 3
                bw, bh = 12 * scale, 10 * scale
                canvas.coords(browser_box, cx-bw, cy-bh+bounce, cx+bw, cy+bh+bounce)
                canvas.coords(browser_line, cx-bw, cy-bh*0.4+bounce, cx+bw, cy-bh*0.4+bounce)
                
            elif visual_state == "BASH":
                target_text = "Bash"
                target_color = '#34d399'
                target_outline = '#065f46'
                show_dots = True
                canvas.itemconfig(sun_glow3, state="hidden")
                canvas.itemconfig(sun_glow2, state="hidden")
                canvas.itemconfig(sun_glow1, state="hidden")
                canvas.itemconfig(core_bg, state="hidden")
                canvas.itemconfig(core_arc1, state="hidden")
                canvas.itemconfig(core_arc2, state="hidden")
                canvas.itemconfig(core_arc3, state="hidden")
                if scale > 0.5:
                    canvas.itemconfig(term_prompt, state="normal" if anim_frame % 20 < 10 else "hidden", font=("Consolas", max(1, int(11 * scale)), "bold"))
                
            elif visual_state == "FILE":
                target_text = "I/O"
                target_color = '#818cf8'
                target_outline = '#3730a3'
                show_dots = True
                canvas.itemconfig(sun_glow3, state="hidden")
                canvas.itemconfig(sun_glow2, state="hidden")
                canvas.itemconfig(sun_glow1, state="hidden")
                canvas.itemconfig(core_bg, state="hidden")
                canvas.itemconfig(core_arc1, state="hidden")
                canvas.itemconfig(core_arc2, state="hidden")
                canvas.itemconfig(core_arc3, state="hidden")
                if scale > 0.5:
                    canvas.itemconfig(file_icon, state="normal")
                bounce = math.sin(anim_frame * 0.1) * 2
                w, h = 6 * scale, 8 * scale
                canvas.coords(file_icon, cx-w, cy-h+bounce, cx+w/2, cy-h+bounce, cx+w+2, cy-h/2+bounce, cx+w+2, cy+h+2+bounce, cx-w, cy+h+2+bounce)

            elif visual_state == "RUNNING":
                target_text = "Processing"
                target_color = '#e5e7eb'
                target_outline = '#374151'
                show_dots = True
                canvas.itemconfig(sun_aura, fill='#1f2937')
                canvas.itemconfig(sun_glow4, fill='#374151')
                canvas.itemconfig(sun_glow3, fill='#4b5563')
                canvas.itemconfig(sun_glow2, fill='#9ca3af')
                canvas.itemconfig(sun_glow1, fill='#d1d5db')
                canvas.itemconfig(core_bg, fill='#ffffff')
                canvas.itemconfig(core_arc1, fill='#e5e7eb')
                canvas.itemconfig(core_arc2, fill='#9ca3af')
                canvas.itemconfig(core_arc3, fill='#d1d5db')
                
            else: # IDLE
                target_text = "Standing by..."
                target_outline = '#27272a'
                canvas.itemconfig(sun_aura, fill='#18181b')
                canvas.itemconfig(sun_glow4, fill='#1e1e24')
                canvas.itemconfig(sun_glow3, fill='#27272a')
                canvas.itemconfig(sun_glow2, fill='#3f3f46')
                canvas.itemconfig(sun_glow1, fill='#71717a')
                canvas.itemconfig(core_bg, fill='#ffffff')
                canvas.itemconfig(core_arc1, fill='#06b6d4')
                canvas.itemconfig(core_arc2, fill='#3b82f6')
                canvas.itemconfig(core_arc3, fill='#0ea5e9')

            if is_hovering_pill:
                canvas.itemconfig(pill, outline='#6666ff')
            else:
                canvas.itemconfig(pill, outline=target_outline)

            # --- Typewriter Animation Logic ---
            global typewriter_idx, typewriter_base, typewriter_target
            
            # If target text changes, reset the typewriter
            if target_text != typewriter_target:
                typewriter_target = target_text
                typewriter_idx = 0
                typewriter_base = ""
                
            # Type 1 character every 2 frames (approx 25 chars per second at 50fps)
            if anim_frame % 2 == 0 and typewriter_idx < len(typewriter_target):
                typewriter_base += typewriter_target[typewriter_idx]
                typewriter_idx += 1
                
            display = typewriter_base
            # Only show dynamic dots if the base word has finished typing
            if show_dots and typewriter_idx >= len(typewriter_target):
                display += dots
                
            if not alert_state["active"]:
                canvas.itemconfig(status_text, text=display, fill=target_color)

    elif dashboard_active and anim_frame % 50 == 0:
        if current_section != 'Settings':
            refresh_dashboard_content()

    root.after(20, animation_loop)
def reset_to_idle():
    global ai_state
    if ai_state != "IDLE":
        ai_state = "IDLE"
        update_expression()

def parse_line(line):
    global ai_state, mobile_clients, glow_timer, current_mode, backend_status

    if not line.startswith("STATUS:"):
        # Non-STATUS lines: use keyword sniffing ONLY as a soft hint, not authoritative
        l = line.lower()
        if ai_state == "RUNNING":
            if "thinking" in l or "planning" in l:     ai_state = "THINKING"
            elif "search" in l or "browse" in l:       ai_state = "SEARCH"
            elif "command" in l or "powershell" in l or "bash" in l: ai_state = "BASH"
            elif "read" in l or "write" in l or "file" in l: ai_state = "FILE"
        return

    # ── Authoritative STATUS: protocol ──────────────────────────────────────
    if "STATUS: GRAPHIFY" in line:
        ai_state = "GRAPHIFY"
        return
        

    if "STATUS: BACKEND:ONLINE" in line:
        if backend_status != "Active":
            backend_status = "Active"
            if dashboard_active and current_section != 'Settings': refresh_dashboard_content()
        return
    if "STATUS: BACKEND:OFFLINE" in line:
        if backend_status != "Offline":
            backend_status = "Offline"
            if dashboard_active and current_section != 'Settings': refresh_dashboard_content()
        return
    
    if "STATUS: MOBILE_CLIENTS:" in line:
        count_str = line.split("STATUS: MOBILE_CLIENTS:")[1].strip()
        try:
            mobile_clients = int(count_str)
            update_expression()
            if dashboard_active and current_section != 'Settings':
                refresh_dashboard_content()
        except: pass
        return

    if "STATUS: IDLE" in line:
        if glow_timer: root.after_cancel(glow_timer)
        glow_timer = root.after(1500, reset_to_idle)
        return

    if "STATUS: FORCE_IDLE" in line:
        if glow_timer: root.after_cancel(glow_timer)
        reset_to_idle()
        return

    if "STATUS: RUNNING" in line:
        if glow_timer: root.after_cancel(glow_timer)
        ai_state = "RUNNING"
        return

    # Real command outcome tracking (from Go's /execute goroutine)
    if "STATUS: CMD_DONE:SUCCESS" in line:
        usage_stats["commands_executed"] += 1
        usage_stats["commands_successful"] += 1
        usage_stats["last_command_time"] = time.time()
        # Update peak commands/min
        session_duration = max(1, int((time.time() - usage_stats['session_start']) / 60))
        cpm = usage_stats["commands_executed"] // session_duration
        if cpm > usage_stats["peak_commands_per_min"]:
            usage_stats["peak_commands_per_min"] = cpm
        return

    if "STATUS: CMD_DONE:FAILED" in line:
        usage_stats["commands_executed"] += 1
        usage_stats["commands_failed"] += 1
        return

    # Real latency tracking
    if "STATUS: LATENCY_MS:" in line:
        try:
            ms = int(line.split("STATUS: LATENCY_MS:")[1].strip())
            # Exponential moving average
            usage_stats["avg_latency_ms"] = int(usage_stats["avg_latency_ms"] * 0.7 + ms * 0.3)
            usage_stats["timeline_data"].append(ms)
            if len(usage_stats["timeline_data"]) > 20:
                usage_stats["timeline_data"].pop(0)
        except: pass
        return

    # Tool-specific face states (from cloud AI tool calls)
    if "STATUS: MODE:" in line:
        # Go confirmed the actual mode used — keep Python in sync
        confirmed_mode = line.split("STATUS: MODE:")[1].strip().upper()
        if confirmed_mode in MODE_LABELS and confirmed_mode != current_mode:
            current_mode = confirmed_mode
            if '_dash_mode_btns' in globals():
                for m, btn in _dash_mode_btns.items():
                    if m == current_mode:
                        btn.config(bg=MODE_COLORS[m], fg='#FFFFFF')
                    else:
                        btn.config(bg='#2D3039', fg='#9CA3AF')
        return

    if "STATUS: TOOL:" in line:
        tool = line.split("STATUS: TOOL:")[1].strip().lower()
        if "web_research" in tool:
            ai_state = "RESEARCH"
        elif "browser_automation" in tool or "browse" in tool:
            ai_state = "BROWSER"
        elif "web_search" in tool or "search" in tool:
            ai_state = "SEARCH"
        elif "run_terminal" in tool or "terminal" in tool:
            ai_state = "BASH"
        elif "read_file" in tool or "write_file" in tool or "file" in tool:
            ai_state = "FILE"
        else:
            ai_state = "THINKING"
        return

import queue as _queue

# Bug #7 Fix: Thread-safe queue for batching output lines.
# The old code did root.after(0, parse_line, line) for EVERY line, which floods
# the Tkinter event loop when the AI outputs verbose code/logs (hundreds of events
# in milliseconds). Now lines go into a queue and are drained in batches every 50ms.
_line_queue = _queue.Queue()

def read_output():
    """Background thread: reads voila.exe stdout line by line into the queue."""
    while True:
        line = agent_process.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line:
            _line_queue.put(line)

def _drain_line_queue():
    """UI thread: drain up to 20 queued lines per tick to stay responsive."""
    for _ in range(20):
        try:
            line = _line_queue.get_nowait()
            parse_line(line)
        except _queue.Empty:
            break
    root.after(50, _drain_line_queue)  # Poll every 50ms

# Resource monitoring background thread removed to drop overhead

t = threading.Thread(target=read_output, daemon=True)
t.start()

# Start the queue drain loop
root.after(50, _drain_line_queue)

update_expression()
animation_loop()


# --- GRAPHIFY TEAMS STATE ---
import math
import os

if 'graph_state' not in globals():
    graph_state = {
        "nodes": [
            {"id": "node1", "role": "Researcher", "model": "openai/gpt-oss-20b\n(Groq)", "prompt": "Analyze the request and propose an initial approach.", "x": 150, "y": 150, "color": "#2563EB", "outline": "#60A5FA", "r": 20},
            {"id": "node2", "role": "Orchestrator", "model": "openai/gpt-oss-120b\n(Groq)", "prompt": "Resolve the debate and improve the approach.", "x": 350, "y": 250, "color": "#7C3AED", "outline": "#A78BFA", "r": 25},
            {"id": "node3", "role": "Reviewer", "model": "openai/gpt-oss-20b\n(Groq)", "prompt": "Critique the approach and point out flaws.", "x": 550, "y": 150, "color": "#10B981", "outline": "#34D399", "r": 20}
        ],
        "edges": [
            ("node1", "node2"),
            ("node2", "node3")
        ],
        "is_custom": False
    }
    drag_data = {"node_id": None, "last_x": 0, "last_y": 0}
    interaction_state = {"selected_node": None}

def export_graphify_prompt():
    prompt_path = "graphify_prompt.txt"
    nodes = graph_state["nodes"]
    edges = graph_state["edges"]
    
    prompt = "GRAPHIFY MULTI-MODEL TEAM PROTOCOL INITIATED.\n\n"
    prompt += "You are an orchestration engine hosting a collaborative workspace for a team of expert AI models. Simulate a strict back-and-forth chat before giving the final answer.\n\n"
    prompt += "REQUIRED WORKFLOW:\n"
    
    node_map = {n['id']: n for n in nodes}
    for i, n in enumerate(nodes):
        prompt += f"{i+1}. [{n['role']}]: {n.get('prompt', '')}\n"
        
    prompt += f"{len(nodes)+1}. [Chunker]: Breaks the final approach down into small, sequential, discrete chunks/steps to prevent failures.\n"
    prompt += f"{len(nodes)+2}. Execute tools step-by-step according to the chunks and finalize.\n\n"
    
    prompt += "DATA FLOW (Follow this strictly):\n"
    if not edges:
        prompt += "- Independent parallel execution.\n"
    for src_id, tgt_id in edges:
        if src_id in node_map and tgt_id in node_map:
            prompt += f"- [{node_map[src_id]['role']}] passes output to [{node_map[tgt_id]['role']}]\n"
            
    prompt += "\nOutput this exact debate transcript before you execute any tools.\n"
    
    try:
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)
            
        import json as _json
        with open("graphify_state.json", "w", encoding="utf-8") as f:
            _json.dump(graph_state, f, indent=2)
    except Exception as e:
        print("Failed to write prompt:", e)

def _draw_teams_section(dc, w, h):
    dc.delete('team_element')
    
    # Header
    dc.create_text(24, 30, text='Graphify Teams (Multi-Model Collaboration)', fill='#E5E7EB', font=('Segoe UI', 16, 'bold'), anchor='w', tags='team_element')
    dc.create_text(24, 55, text='Drag & drop nodes. Click two nodes to connect/disconnect. Drop on line to split.', fill='#9CA3AF', font=('Segoe UI', 10), anchor='w', tags='team_element')
    
    # Background Box
    dc.create_rectangle(20, 80, w - 20, 320, fill='#1A1D23', outline='#374151', width=1, tags='team_element')
    
    node_map = {n['id']: n for n in graph_state['nodes']}
    
    # Draw edges
    for src, tgt in graph_state['edges']:
        if src in node_map and tgt in node_map:
            n1 = node_map[src]
            n2 = node_map[tgt]
            tag = f'edge_{src}_{tgt}'
            dc.create_line(n1['x'], n1['y'], n2['x'], n2['y'], fill='#4F46E5', width=3, dash=(4,4), tags=('team_element', tag, 'edge_line'))
            
    # Draw nodes
    for i, n in enumerate(graph_state['nodes']):
        x, y, r = n['x'], n['y'], n['r']
        nid = n['id']
        outline_color = "#FBBF24" if interaction_state["selected_node"] == nid else n['outline']
        outline_width = 4 if interaction_state["selected_node"] == nid else 2
        
        # Node Oval
        dc.create_oval(x-r, y-r, x+r, y+r, fill=n['color'], outline=outline_color, width=outline_width, tags=('team_element', f'node_{nid}', f'circle_{nid}', 'draggable'))
        # Number inside
        dc.create_text(x, y, text=str(i+1), fill='white', font=('Segoe UI', max(10, r-8), 'bold'), tags=('team_element', f'node_{nid}', f'text1_{nid}', 'draggable'))
        # Role Label
        dc.create_text(x, y - r - 15, text=n['role'], fill='#D1D5DB', font=('Segoe UI', 10, 'bold'), tags=('team_element', f'node_{nid}', f'text2_{nid}', 'draggable'))
        # Model Label
        dc.create_text(x, y + r + 15, text=n['model'], fill='#9CA3AF', font=('Segoe UI', 9), justify='center', tags=('team_element', f'node_{nid}', f'text3_{nid}', 'draggable'))
        
    # Button: New Team
    dc.create_rectangle(24, 340, 140, 375, fill='#4F46E5', outline='', tags=('team_element', 'btn_add_team'))
    dc.create_text(82, 357, text='+ New Team', fill='white', font=('Segoe UI', 10, 'bold'), tags=('team_element', 'btn_add_team'))
    
    # Button: Edit Models
    dc.create_rectangle(150, 340, 270, 375, fill='#374151', outline='', tags=('team_element', 'btn_edit_team'))
    dc.create_text(210, 357, text='Edit Models', fill='white', font=('Segoe UI', 10, 'bold'), tags=('team_element', 'btn_edit_team'))

    # --- Interaction Logic ---
    
    def on_node_press(e):
        items = dc.find_withtag("current")
        if not items: return
        tags = dc.gettags(items[0])
        for tag in tags:
            if tag.startswith('node_'):
                nid = tag.replace('node_', '')
                drag_data['node_id'] = nid
                drag_data['last_x'] = e.x
                drag_data['last_y'] = e.y
                drag_data['start_x'] = e.x
                drag_data['start_y'] = e.y
                drag_data['dragged'] = False
                break

    def on_drag_motion(e):
        nid = drag_data.get('node_id')
        if nid:
            if not drag_data.get('dragged'):
                if abs(e.x - drag_data.get('start_x', e.x)) > 3 or abs(e.y - drag_data.get('start_y', e.y)) > 3:
                    drag_data['dragged'] = True
                    
            dx = e.x - drag_data['last_x']
            dy = e.y - drag_data['last_y']
            
            node = next((n for n in graph_state['nodes'] if n['id'] == nid), None)
            if node:
                new_x = min(max(node['x'] + dx, 40), w - 40)
                new_y = min(max(node['y'] + dy, 120), 280)
                
                actual_dx = new_x - node['x']
                actual_dy = new_y - node['y']
                
                node['x'] = new_x
                node['y'] = new_y
                
                dc.move(f'circle_{nid}', actual_dx, actual_dy)
                dc.move(f'text1_{nid}', actual_dx, actual_dy)
                dc.move(f'text2_{nid}', actual_dx, actual_dy)
                dc.move(f'text3_{nid}', actual_dx, actual_dy)
                
                node_map = {n['id']: n for n in graph_state['nodes']}
                for src, tgt in graph_state['edges']:
                    if src == nid or tgt == nid:
                        if src in node_map and tgt in node_map:
                            dc.coords(f'edge_{src}_{tgt}', node_map[src]['x'], node_map[src]['y'], node_map[tgt]['x'], node_map[tgt]['y'])
                
            drag_data['last_x'] = e.x
            drag_data['last_y'] = e.y

    def pt_line_dist(px, py, x1, y1, x2, y2):
        l2 = (x2 - x1)**2 + (y2 - y1)**2
        if l2 == 0: return math.hypot(px - x1, py - y1)
        t = max(0, min(1, ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2))
        proj_x = x1 + t * (x2 - x1)
        proj_y = y1 + t * (y2 - y1)
        return math.hypot(px - proj_x, py - proj_y)

    def on_drag_stop(e):
        nid = drag_data.get('node_id')
        dragged = drag_data.get('dragged', False)
        drag_data['node_id'] = None
        
        if not nid: return
        
        if not dragged:
            # PURE CLICK -> Selection / Connection logic
            sel = interaction_state["selected_node"]
            if sel is None:
                interaction_state["selected_node"] = nid
                _draw_teams_section(dc, w, h)
            elif sel == nid:
                interaction_state["selected_node"] = None
                _draw_teams_section(dc, w, h)
            else:
                edge1 = (sel, nid)
                if edge1 in graph_state['edges']:
                    graph_state['edges'].remove(edge1)
                else:
                    graph_state['edges'].append(edge1)
                interaction_state["selected_node"] = None
                graph_state['is_custom'] = True
                export_graphify_prompt()
                _draw_teams_section(dc, w, h)
        else:
            # DROP -> Edge Splitting logic
            node = next((n for n in graph_state['nodes'] if n['id'] == nid), None)
            if not node: return
            
            node_map = {n['id']: n for n in graph_state['nodes']}
            split_edge = None
            for edge in graph_state['edges']:
                src, tgt = edge
                if src == nid or tgt == nid: continue
                if src in node_map and tgt in node_map:
                    d = pt_line_dist(node['x'], node['y'], node_map[src]['x'], node_map[src]['y'], node_map[tgt]['x'], node_map[tgt]['y'])
                    if d < 35: # Generous drop tolerance
                        min_x = min(node_map[src]['x'], node_map[tgt]['x']) - 35
                        max_x = max(node_map[src]['x'], node_map[tgt]['x']) + 35
                        min_y = min(node_map[src]['y'], node_map[tgt]['y']) - 35
                        max_y = max(node_map[src]['y'], node_map[tgt]['y']) + 35
                        if min_x <= node['x'] <= max_x and min_y <= node['y'] <= max_y:
                            split_edge = edge
                            break
                            
            if split_edge:
                graph_state['edges'].remove(split_edge)
                graph_state['edges'].append((split_edge[0], nid))
                graph_state['edges'].append((nid, split_edge[1]))
                export_graphify_prompt()
                _draw_teams_section(dc, w, h)

    dc.tag_bind('draggable', '<ButtonPress-1>', on_node_press)
    dc.bind('<B1-Motion>', on_drag_motion)
    dc.bind('<ButtonRelease-1>', on_drag_stop)
    dc.tag_bind('draggable', '<Enter>', lambda e: dc.config(cursor='hand2'))
    dc.tag_bind('draggable', '<Leave>', lambda e: dc.config(cursor=''))

    # Popup Editor
    def on_edit_team(e):
        top = tk.Toplevel()
        top.title("Edit Graphify Team")
        top.geometry("500x550")
        top.configure(bg='#0F1115')
        top.attributes('-topmost', True)
        
        tk.Label(top, text="Configure Model Chain & Prompts", bg='#0F1115', fg='white', font=('Segoe UI', 14, 'bold')).pack(pady=10)
        
        frame = tk.Frame(top, bg='#0F1115')
        frame.pack(fill='both', expand=True, padx=20)
        
        canvas = tk.Canvas(frame, bg='#0F1115', highlightthickness=0)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#0F1115')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        import copy
        import time as _time
        editor_nodes = copy.deepcopy(graph_state['nodes'])
        entries = []
        
        def render_nodes():
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            entries.clear()
            
            groq_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound", "groq/compound-mini", "qwen/qwen3.8-27b", "allam-2-7b"]
            ollama_models = ["gemma4:31b", "gpt-oss:120b", "gpt-oss:20b", "nemotron-3-nano:30b", "nemotron-3-super", "nemotron-3-ultra"]
            
            for i, n in enumerate(editor_nodes):
                row = tk.Frame(scrollable_frame, bg='#1A1D23', bd=1, relief='solid', pady=5, padx=5)
                row.pack(fill='x', pady=5, padx=5)
                
                top_row = tk.Frame(row, bg='#1A1D23')
                top_row.pack(fill='x')
                tk.Label(top_row, text=f"Node {i+1} Role:", bg='#1A1D23', fg='#D1D5DB').pack(side='left')
                role_entry = tk.Entry(top_row, width=12, bg='#374151', fg='white', insertbackground='white', relief='flat')
                role_entry.insert(0, n.get('role', ''))
                role_entry.pack(side='left', padx=2)
                
                tk.Label(top_row, text="Prov:", bg='#1A1D23', fg='#D1D5DB').pack(side='left')
                prov_var = tk.StringVar()
                model_var = tk.StringVar()
                
                existing_model = n.get('model', '')
                curr_prov = "Groq"
                curr_mod = groq_models[1]
                if '(Ollama)' in existing_model:
                    curr_prov = "Ollama"
                    curr_mod = existing_model.replace('\n(Ollama)', '').replace('(Ollama)', '').strip()
                elif '(Groq)' in existing_model:
                    curr_prov = "Groq"
                    curr_mod = existing_model.replace('\n(Groq)', '').replace('(Groq)', '').strip()
                
                prov_var.set(curr_prov)
                model_var.set(curr_mod)
                
                import tkinter.ttk as ttk
                style = ttk.Style()
                if 'Dark.TCombobox' not in style.theme_names():
                    try: style.theme_use('clam')
                    except: pass
                    style.configure('Dark.TCombobox', fieldbackground='#374151', background='#374151', foreground='white')
                
                model_cb = ttk.Combobox(top_row, textvariable=model_var, style='Dark.TCombobox', width=16, state='readonly')
                
                def on_prov_change(event, cb=model_cb, mv=model_var, pv=prov_var):
                    if pv.get() == "Groq":
                        cb['values'] = groq_models
                        if mv.get() not in groq_models: mv.set(groq_models[1])
                    else:
                        cb['values'] = ollama_models
                        if mv.get() not in ollama_models: mv.set(ollama_models[0])
                        
                prov_cb = ttk.Combobox(top_row, textvariable=prov_var, values=["Groq", "Ollama"], style='Dark.TCombobox', width=7, state='readonly')
                prov_cb.bind('<<ComboboxSelected>>', on_prov_change)
                prov_cb.pack(side='left', padx=2)
                
                if curr_prov == "Groq": model_cb['values'] = groq_models
                else: model_cb['values'] = ollama_models
                
                model_cb.pack(side='left', padx=2)
                
                tk.Button(top_row, text="X", bg='#EF4444', fg='white', relief='flat', command=lambda idx=i: delete_node(idx)).pack(side='right', padx=2)
                
                bot_row = tk.Frame(row, bg='#1A1D23')
                bot_row.pack(fill='x', pady=5)
                tk.Label(bot_row, text="Prompt:", bg='#1A1D23', fg='#D1D5DB').pack(side='left', anchor='n')
                prompt_text = tk.Text(bot_row, height=3, width=45, bg='#374151', fg='white', insertbackground='white', relief='flat')
                prompt_text.insert('1.0', n.get('prompt', ''))
                prompt_text.pack(side='left', padx=5)
                
                entries.append((role_entry, model_var, prov_var, prompt_text))
                
        def sync_entries():
            for i, (r_ent, m_var, p_var, p_txt) in enumerate(entries):
                editor_nodes[i]['role'] = r_ent.get()
                editor_nodes[i]['model'] = m_var.get() + '\n(' + p_var.get() + ')'
                editor_nodes[i]['prompt'] = p_txt.get('1.0', 'end').strip()
                
        def add_node():
            sync_entries()
            import time as _time
            new_id = f"node{int(_time.time()*1000)}"
            editor_nodes.append({
                "id": new_id, "role": "Agent", "model": "openai/gpt-oss-20b\n(Groq)", 
                "prompt": "", "x": 250, "y": 200, "color": "#10B981", "outline": "#34D399", "r": 20
            })
            render_nodes()
            
        def delete_node(idx):
            sync_entries()
            if len(editor_nodes) > 0:
                editor_nodes.pop(idx)
                render_nodes()
                
        
            sync_entries()
            if len(editor_nodes) > 0:
                editor_nodes.pop(idx)
                render_nodes()
                
        render_nodes()
        
        btn_frame = tk.Frame(top, bg='#0F1115')
        btn_frame.pack(fill='x', pady=10)
        
        tk.Button(btn_frame, text="+ Add Node", command=add_node, bg='#4F46E5', fg='white', relief='flat').pack(side='left', padx=20)
        
        def save_changes():
            sync_entries()
            graph_state['nodes'] = editor_nodes
            
            valid_ids = {n['id'] for n in editor_nodes}
            graph_state['is_custom'] = True
            graph_state['edges'] = [e for e in graph_state['edges'] if e[0] in valid_ids and e[1] in valid_ids]
            
            export_graphify_prompt()
            _draw_teams_section(dc, w, h)
            top.destroy()
            
        tk.Button(btn_frame, text="Save & Update", command=save_changes, bg='#10B981', fg='white', relief='flat').pack(side='right', padx=20)
        
    def on_new_team(e):
        global graph_state
        graph_state = {
            "nodes": [
                {"id": "node1", "role": "Analyzer", "model": "openai/gpt-oss-20b\n(Groq)", "prompt": "Analyze", "x": 100, "y": 200, "color": "#F59E0B", "outline": "#FCD34D", "r": 20},
                {"id": "node2", "role": "Writer", "model": "openai/gpt-oss-20b\n(Groq)", "prompt": "Write", "x": w//2, "y": 200, "color": "#3B82F6", "outline": "#93C5FD", "r": 20},
            ],
            "edges": [], "is_custom": True
        }
        interaction_state["selected_node"] = None
        export_graphify_prompt()
        _draw_teams_section(dc, w, h)

    dc.tag_bind('btn_edit_team', '<Enter>', lambda e: dc.config(cursor='hand2'))
    dc.tag_bind('btn_edit_team', '<Leave>', lambda e: dc.config(cursor=''))
    dc.tag_bind('btn_edit_team', '<Button-1>', on_edit_team)
    
    dc.tag_bind('btn_add_team', '<Enter>', lambda e: dc.config(cursor='hand2'))
    dc.tag_bind('btn_add_team', '<Leave>', lambda e: dc.config(cursor=''))
    dc.tag_bind('btn_add_team', '<Button-1>', on_new_team)

# Write initial prompt file if not exists
export_graphify_prompt()

root.mainloop()
