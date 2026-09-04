import tkinter as tk
from tkinter import ttk
import subprocess
import threading
import sys
import time
import math
import random

# Removed psutil import completely as per user request to drop overhead
PSUTIL_AVAILABLE = False

import logging as _logging
_voila_log = _logging.getLogger('voila_py')
_voila_log.setLevel(_logging.DEBUG)
_voila_fh = _logging.FileHandler(
    r'C:\Users\ojasw\Desktop\voice-cli-system\local-agent\voila_debug.log',
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

x = root.winfo_screenwidth() - 320
y = root.winfo_screenheight() - 120
root.geometry(f"+{x}+{y}")

canvas = tk.Canvas(root, width=300, height=90, bg='magenta', highlightthickness=0)
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
snot_bubble = canvas.create_oval(0, 0, 0, 0, fill='', outline='#aaddff', width=1.5, state='hidden')
snot_shine = canvas.create_oval(0, 0, 0, 0, fill='#ffffff', outline='', state='hidden')
zzz1 = canvas.create_text(0, 0, text="Z", fill='#aaddff', font=("Segoe UI", 12, "bold"), state='hidden')
zzz2 = canvas.create_text(0, 0, text="z", fill='#aaddff', font=("Segoe UI", 10, "bold"), state='hidden')
zzz3 = canvas.create_text(0, 0, text="z", fill='#aaddff', font=("Segoe UI", 8, "bold"), state='hidden')

face_parts = (body, arm_l, arm_r, leg1, leg2, leg3, leg4, eye_l, eye_r, eye_l_shine, eye_r_shine, snot_bubble, snot_shine, zzz1, zzz2, zzz3)

# Perfectly positioned Title (x=90)
title_text = canvas.create_text(90, 45, text="Voila", fill="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")

# Perfectly centered status in the cloud (x=150+55=205)
status_text = canvas.create_text(cx+55, cy+25, text="Standing by...", fill="#888888", font=("Segoe UI", 8, "italic"), anchor="center", width=150)

# Close Button - larger clickable area for better hit detection
close_btn_bg = canvas.create_oval(245, 25, 295, 65, fill="", outline="", width=0, state='hidden')
close_btn = canvas.create_text(270, 45, text="✕", fill="#888888", font=("Segoe UI", 20, "bold"), anchor="center")

# ── LOCAL/CLOUD mode toggle  ───────────────────────────────────────────
MODES = ["LOCAL", "GROQ", "OLLAMA"]
MODE_COLORS = {"LOCAL": "#6366F1", "GROQ": "#10B981", "OLLAMA": "#F59E0B"}
MODE_LABELS = {"LOCAL": "⚡LOCAL", "GROQ": "☁ GROQ", "OLLAMA": "🦙OLLAMA"}
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

# Add hover effect for dashboard toggle
def on_enter_pill(e): 
    if not dashboard_active and not dashboard_transition_in_progress:
        canvas.itemconfig(pill, outline='#6666ff')
def on_leave_pill(e): 
    if not dashboard_active and not dashboard_transition_in_progress:
        canvas.itemconfig(pill, outline='#3a3a40')

def on_enter_close(e):
    if dashboard_active:
        try:
            canvas.itemconfig("close_btn_bg", fill="#DC2626", outline="#B91C1C")  # Darker red on hover
        except:
            pass
    else:
        canvas.itemconfig(close_btn, fill="#ff5555")
        canvas.itemconfig(close_btn_bg, state='normal', fill="#ff5555", outline="#DC2626")

def on_leave_close(e):
    if dashboard_active:
        try:
            canvas.itemconfig("close_btn_bg", fill="#EF4444", outline="#B91C1C")  # Restore red
        except:
            pass
    else:
        canvas.itemconfig(close_btn, fill="#888888")
        canvas.itemconfig(close_btn_bg, state='hidden')

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
current_width = 300
current_height = 90
target_width = 300
target_height = 90
transition_progress = 0.0
transition_in_progress = False

# Resource monitoring functions removed to drop overhead

def update_expression():
    global ai_state, alert_state
    if dashboard_active or dashboard_transition_in_progress:
        return
    if mobile_clients == 0:
        # ASLEEP / OFFLINE (but wake up for resource alerts)
        canvas.itemconfig(pill, outline='#3a3a40', fill='#1e1e24')
        
        # Show cloud if resource alert is active
        if alert_state["active"]:
            for cp in cloud_parts: canvas.itemconfig(cp, state='normal', fill='#ffaa00')  # Orange for alert
            alert_msg = alert_state["message"]
            apps = alert_state["apps"]
            if apps:
                alert_msg += "\n• " + "\n• ".join(apps)
            canvas.itemconfig(status_text, state='normal', text=alert_msg, fill='#ff5555', font=("Segoe UI", 9, "bold"))
            canvas.itemconfig(pill, outline='#ff5555', fill='#2a1a1a')
            
            # Update text width for alert
            if current_width != target_width:
                canvas.itemconfig(status_text, width=max(150, target_width - 120))
            
            # Eyes alert (red, wide open)
            canvas.coords(eye_l, sx+22, sy+28, sx+32, sy+38)
            canvas.coords(eye_r, sx+48, sy+28, sx+58, sy+38)
            canvas.itemconfig(eye_l, fill='#ff5555')
            canvas.itemconfig(eye_r, fill='#ff5555')
            canvas.itemconfig(eye_l_shine, state='normal')
            canvas.itemconfig(eye_r_shine, state='normal')
        else:
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
            
            # Hide alert elements
            canvas.itemconfig(snot_bubble, state='hidden')
            canvas.itemconfig(snot_shine, state='hidden')
            canvas.itemconfig(zzz1, state='hidden')
            canvas.itemconfig(zzz2, state='hidden')
            canvas.itemconfig(zzz3, state='hidden')

    else:
        # NORMAL / IDLE / WORKING
        canvas.itemconfig(pill, outline='#3a3a40', fill='#1e1e24')
        for cp in cloud_parts: canvas.itemconfig(cp, state='normal', fill='#2a2a32')
        
        # Show alert in cloud if active
        if alert_state["active"]:
            alert_msg = alert_state["message"]
            apps = alert_state["apps"]
            if apps:
                alert_msg += "\n• " + "\n• ".join(apps)
            canvas.itemconfig(status_text, state='normal', text=alert_msg, fill='#ff5555', font=("Segoe UI", 9, "bold"))
            canvas.itemconfig(pill, outline='#ff5555', fill='#2a1a1a')
            
            # Update text width for alert
            if current_width != target_width:
                canvas.itemconfig(status_text, width=max(150, target_width - 120))
        else:
            canvas.itemconfig(status_text, state='normal', text="Standing by...", fill='#888888', font=("Segoe UI", 8, "italic"))
            canvas.itemconfig(pill, outline='#3a3a40', fill='#1e1e24')
        
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
        canvas.itemconfig(snot_shine, state='hidden')
        canvas.itemconfig(zzz1, state='hidden')
        canvas.itemconfig(zzz2, state='hidden')
        canvas.itemconfig(zzz3, state='hidden')

# Dashboard state (separate from alert resizing to avoid conflicts)
dashboard_active = False
dashboard_transition_in_progress = False
dashboard_transition_progress = 0.0
original_pos = (0, 0)  # Store original position
original_size = (300, 90)  # Store original size
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
DASHBOARD_W = 920
DASHBOARD_H = 620

def hide_mini_popup_elements():
    """Hide mini widget canvas while dashboard is shown."""
    canvas.pack_forget()

def restore_mini_popup_elements(w=300, h=90):
    """Fully restore the compact widget layout and styling."""
    global sx, sy, cx, cy, heatmap_cache, current_width, current_height

    sx, sy = 15, 10
    cx, cy = 150, 15
    heatmap_cache = None
    current_width = w
    current_height = h

    canvas.config(bg='magenta', width=w, height=h)
    canvas.pack(fill='both', expand=True)

    set_round_rect(pill, 10, 10, w - 10, h - 10, 20)
    canvas.itemconfig(pill, state='normal', fill=bg_idle, outline=border_idle, width=2)

    canvas.coords(body, sx + 15, sy + 15, sx + 65, sy + 55)
    canvas.coords(arm_l, sx + 8, sy + 30, sx + 15, sy + 45)
    canvas.coords(arm_r, sx + 65, sy + 30, sx + 72, sy + 45)
    canvas.coords(leg1, sx + 15, sy + 55, sx + 23, sy + 70)
    canvas.coords(leg2, sx + 28, sy + 55, sx + 36, sy + 70)
    canvas.coords(leg3, sx + 44, sy + 55, sx + 52, sy + 70)
    canvas.coords(leg4, sx + 57, sy + 55, sx + 65, sy + 70)
    canvas.coords(eye_l, sx + 22, sy + 28, sx + 32, sy + 38)
    canvas.coords(eye_r, sx + 48, sy + 28, sx + 58, sy + 38)
    canvas.coords(eye_l_shine, sx + 27, sy + 30, sx + 30, sy + 33)
    canvas.coords(eye_r_shine, sx + 53, sy + 30, sx + 56, sy + 33)

    canvas.coords(c_dot1, 90, 40, 95, 45)
    canvas.coords(c_dot2, 110, 30, 120, 40)
    canvas.coords(c_dot3, 130, 20, 145, 35)
    canvas.coords(c_oval1, cx, cy + 10, cx + 40, cy + 50)
    canvas.coords(c_oval2, cx + 20, cy, cx + 80, cy + 60)
    canvas.coords(c_oval3, cx + 60, cy + 10, cx + 110, cy + 50)
    canvas.coords(c_oval4, cx + 40, cy - 5, cx + 100, cy + 45)

    canvas.coords(title_text, 90, 45)
    canvas.itemconfig(title_text, state='normal', fill="#ffffff", font=("Segoe UI", 12, "bold"))

    canvas.coords(status_text, cx + 55, cy + 25)
    canvas.itemconfig(status_text, state='normal', width=150)

    canvas.coords(close_btn_bg, 245, 25, 295, 65)
    canvas.itemconfig(close_btn_bg, state='hidden', fill="", outline="")
    canvas.coords(close_btn, w - 25, h // 2)
    canvas.itemconfig(close_btn, state='normal', fill="#888888", font=("Segoe UI", 20, "bold"))
    
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
        header, text='✕', command=toggle_dashboard,
        bg='#EF4444', fg='#FFFFFF', activebackground='#DC2626', activeforeground='#FFFFFF',
        relief='flat', bd=0, width=3, font=('Segoe UI', 12, 'bold'), cursor='hand2',
    )
    close_dash.pack(side='right', padx=(0, 8))

    # ── Mode Toggle Pill (in dashboard header) ──────────────────────────────
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

    tk.Label(dash_sidebar, text='⚡', bg='#16171C', fg='#FFFFFF', font=('Segoe UI', 18)).pack(pady=(16, 0))
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

# ── Settings widget state ────────────────────────────────────────────────────
_settings_frame_widget = None

def _make_btn(parent, text, cmd, bg='#374151', fg='#E5E7EB', width=8):
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                     activebackground='#4B5563', activeforeground='#fff',
                     relief='flat', bd=0, font=('Segoe UI', 9), cursor='hand2',
                     padx=6, pady=4, width=width)

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

def _hide_settings_widgets():
    global _settings_frame_widget
    if _settings_frame_widget:
        _settings_frame_widget.destroy()
        _settings_frame_widget = None

def _show_settings_widgets():
    global _settings_frame_widget
    _hide_settings_widgets()

    # Fetch current values from agent
    data = _api_call('GET', '/api-keys')

    frame = tk.Frame(dash_content, bg='#0F1115')
    frame.place(x=0, y=0, relwidth=1.0, relheight=1.0)
    _settings_frame_widget = frame

    # ── Scrollable container ─────────────────────────────────────────────────
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
    tk.Label(inner, text='⚙  API Keys & Cloud Settings', bg='#0F1115', fg='#E5E7EB',
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

    # Groq Model Dropdown
    tk.Label(groq_frame, text='Model:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=1, column=0, padx=12, pady=4, sticky='w')
    
    groq_models = [
        "llama3-70b-8192",
        "llama3-8b-8192",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-groq-70b-8192-tool-use-preview",
        "llama3-groq-8b-8192-tool-use-preview",
        "mixtral-8x7b-32768",
        "gemma2-9b-it"
    ]
    groq_model_var = tk.StringVar(value=data.get('groq_model', 'llama3-70b-8192') or 'llama3-70b-8192')
    
    style = ttk.Style()
    style.theme_use('default')
    style.configure('TCombobox', fieldbackground='#2D3039', background='#1A1D23', foreground='white')
    
    groq_model_cb = ttk.Combobox(groq_frame, textvariable=groq_model_var, values=groq_models, width=38, font=('Segoe UI', 9))
    groq_model_cb.grid(row=1, column=1, columnspan=2, padx=6, pady=4, sticky='w')
    tk.Label(groq_frame, text='(Free tier + tool calling)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=1, column=3, sticky='w')

    def on_groq_save():
        key = groq_key_var.get().strip()
        model = groq_model_var.get().strip()
        if not key:
            groq_status_var.set('⚠️ Enter a key first')
            groq_status_lbl.config(fg='#F59E0B')
            return
        res = _api_call('POST', '/api-keys', {'groq_api_key': key, 'groq_model': model, 'action': 'save'})
        if 'error' in res:
            groq_status_var.set(f'❌ {res["error"][:40]}')
            groq_status_lbl.config(fg='#EF4444')
        else:
            groq_status_var.set('✅ Saved')
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
    btn_row.grid(row=2, column=0, columnspan=4, padx=12, pady=(0, 10), sticky='w')
    _make_btn(btn_row, '💾 Save', on_groq_save, bg='#6366F1', width=9).pack(side='left', padx=(0, 6))
    _make_btn(btn_row, '✓ Verify', on_groq_verify, bg='#10B981', width=9).pack(side='left', padx=(0, 6))
    _make_btn(btn_row, '🗑 Delete', on_groq_delete, bg='#DC2626', width=9).pack(side='left')

    tk.Label(groq_frame, text='Free models: llama3-70b-8192, llama3-8b-8192, mixtral-8x7b-32768, gemma2-9b-it',
             bg='#1A1D23', fg='#4B5563', font=('Segoe UI', 8, 'italic')).grid(
        row=3, column=0, columnspan=4, padx=12, pady=(0, 10), sticky='w')

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
        row=1, column=0, padx=12, pady=4, sticky='w')
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
    ollama_model_cb.grid(row=1, column=1, columnspan=2, padx=6, pady=4, sticky='w')
    tk.Label(ollama_frame, text='(Free tier + tool calling)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=1, column=3, sticky='w')

    tk.Label(ollama_frame, text='API Key (Opt):', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(
        row=2, column=0, padx=12, pady=4, sticky='w')
    ollama_key_var = tk.StringVar(value=data.get('ollama_api_key_set') == 'true' and '********' or '')
    tk.Entry(ollama_frame, textvariable=ollama_key_var, bg='#2D3039', fg='#E5E7EB',
             insertbackground='#E5E7EB', relief='flat', font=('Segoe UI', 9), width=42, show='*').grid(
        row=2, column=1, columnspan=3, padx=6, pady=4, sticky='ew')

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
    ollama_status_lbl.grid(row=3, column=0, columnspan=4, padx=12, pady=(0, 4), sticky='w')

    def on_ollama_save():
        url = ollama_url_var.get().strip()
        model = ollama_model_var.get().strip()
        key = ollama_key_var.get().strip()
        if key == '********': key = '' # Don't resave placeholder
        if not url:
            ollama_status_var.set('⚠️ Enter Base URL first')
            ollama_status_lbl.config(fg='#F59E0B')
            return
        res = _api_call('POST', '/api-keys', {'ollama_base_url': url, 'ollama_model': model, 'ollama_api_key': key, 'action': 'save'})
        if 'error' in res:
            ollama_status_var.set(f'❌ {res["error"][:40]}')
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
    obtn_row.grid(row=4, column=0, columnspan=4, padx=12, pady=(0, 10), sticky='w')
    _make_btn(obtn_row, '💾 Save', on_ollama_save, bg='#D97706', width=9).pack(side='left', padx=(0, 6))
    _make_btn(obtn_row, '✓ Verify', on_ollama_verify, bg='#10B981', width=9).pack(side='left', padx=(0, 6))
    _make_btn(obtn_row, '🗑 Delete', on_ollama_delete, bg='#DC2626', width=9).pack(side='left')

    tk.Label(ollama_frame, text='Ollama Cloud free models: gemma4:31b, gpt-oss:120b, nemotron-3-nano:30b, ...',
             bg='#1A1D23', fg='#4B5563', font=('Segoe UI', 8, 'italic')).grid(
        row=5, column=0, columnspan=4, padx=12, pady=(0, 10), sticky='w')

    # ─── Info footer ─────────────────────────────────────────────────────────
    info = tk.Frame(inner, bg='#0F1115')
    info.grid(row=3, column=0, columnspan=4, padx=16, pady=12, sticky='ew')
    tk.Label(info, text='Version: 1.0.0  |  Platform: Windows  |  Build: Stable',
             bg='#0F1115', fg='#374151', font=('Segoe UI', 9)).pack(anchor='w')

def refresh_dashboard_content():

    global dash_canvas
    if not dashboard_active or dash_canvas is None:
        return

    # Always destroy settings widget frame when refreshing (navigated away)
    if current_section != 'Settings':
        _hide_settings_widgets()

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
    t_val = time.time()
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

def open_dashboard():
    global dashboard_active, heatmap_cache, current_width, current_height
    build_dashboard_ui()
    heatmap_cache = None
    dashboard_active = True
    hide_mini_popup_elements()

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - DASHBOARD_W) // 2
    y = (screen_h - DASHBOARD_H) // 2
    root.geometry(f'{DASHBOARD_W}x{DASHBOARD_H}+{x}+{y}')
    current_width = DASHBOARD_W
    current_height = DASHBOARD_H

    dashboard_frame.pack(fill='both', expand=True)
    root.update_idletasks()
    refresh_dashboard_content()

def close_dashboard():
    global dashboard_active, heatmap_cache, current_width, current_height
    dashboard_active = False
    heatmap_cache = None
    dashboard_frame.pack_forget()
    root.geometry(f'300x90+{original_pos[0]}+{original_pos[1]}')
    current_width = 300
    current_height = 90
    restore_mini_popup_elements(300, 90)

def ensure_heatmap_cache():
    global heatmap_cache
    # Animate smoothly without full random flicker
    cache = []
    t = time.time()
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
    """Instant switch between mini popup canvas and dashboard frame."""
    global original_pos, original_size
    if not dashboard_active:
        original_pos = (root.winfo_x(), root.winfo_y())
        original_size = (300, 90)
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
    new_cx = new_width // 2
    new_close_x = new_width - 25
    new_cy = new_height // 2 - 10
    
    # Update cloud position
    canvas.coords(c_dot1, new_cx-60, new_cy+15, new_cx-55, new_cy+20)
    canvas.coords(c_dot2, new_cx-40, new_cy+5, new_cx-30, new_cy+15)
    canvas.coords(c_dot3, new_cx-20, new_cy-5, new_cx-5, new_cy+10)
    canvas.coords(c_oval1, new_cx, new_cy, new_cx+40, new_cy+40)
    canvas.coords(c_oval2, new_cx+20, new_cy-10, new_cx+80, new_cy+50)
    canvas.coords(c_oval3, new_cx+60, new_cy, new_cx+110, new_cy+40)
    canvas.coords(c_oval4, new_cx+40, new_cy-15, new_cx+100, new_cy+35)
    
    # Update status text position
    canvas.coords(status_text, new_cx+55, new_cy+10)
    canvas.itemconfig(status_text, width=max(150, new_width - 120))
    
    # Update close button position
    canvas.coords(close_btn, new_close_x, 45)
    
    # Update pill outline to match new width
    set_round_rect(pill, 10, 10, new_width - 10, new_height - 10, 20)
    
    # Update global positions
    cx = new_cx
    cy = new_cy
    
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
    global anim_frame, usage_stats
    anim_frame += 1
    dots = "." * (anim_frame % 4)

    if not dashboard_active and not dashboard_transition_in_progress:
        # usage_stats are now updated in real-time via STATUS: protocol messages
        # (STATUS: CMD_DONE:SUCCESS/FAILED, STATUS: LATENCY_MS:N)

        if alert_state.get("state_changed"):
            update_expression()
            alert_state["state_changed"] = False

        if mobile_clients == 0:
            # Animate Sleep Mode (but preserve alert text if active)
            if not alert_state["active"]:
                canvas.itemconfig(status_text, text=f"Offline (Zzz{dots})", fill='#888888')

            # Snot Bubble expansion/contraction (only if no alert)
            if not alert_state["active"]:
                canvas.itemconfig(snot_bubble, state='normal')
                canvas.itemconfig(snot_shine, state='normal')
                bubble_phase = anim_frame % 24
                if bubble_phase < 20:
                    # Inflate exponentially (0 to 19): grows slowly then pops out at the end
                    t = bubble_phase / 19.0
                    br = 2 + 8 * (t ** 3)
                else:
                    # Deflate quickly (20 to 23)
                    t = (23 - bubble_phase) / 3.0
                    br = 2 + 8 * t
                bx, by = sx + 40, sy + 40
                # Teardrop oval: anchors near the nose at the top, stretches downwards
                canvas.coords(snot_bubble, bx - br, by, bx + br, by + br * 2.5)
                # Shine patch in top-right of the bubble
                canvas.coords(snot_shine, bx + br*0.2, by + br*0.4, bx + br*0.7, by + br*1.0)
            else:
                canvas.itemconfig(snot_bubble, state='hidden')
                canvas.itemconfig(snot_shine, state='hidden')

            # Zzz flying animation (only if no alert)
            if not alert_state["active"]:
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
            else:
                canvas.itemconfig(zzz1, state='hidden')
                canvas.itemconfig(zzz2, state='hidden')
                canvas.itemconfig(zzz3, state='hidden')

        elif ai_state != "IDLE":
            canvas.itemconfig(pill, fill='#22222a')
            canvas.itemconfig(status_text, state='normal')
            for cp in cloud_parts:
                canvas.itemconfig(cp, state='normal', fill='#33333d')

            pulse = (anim_frame % 6)
            if pulse > 3:
                pulse = 6 - pulse
            ew = 4 + pulse

            elx, ely = sx + 27, sy + 33
            erx, ery = sx + 53, sy + 33

            canvas.coords(eye_l, elx - ew, ely - ew, elx + ew, ely + ew)
            canvas.coords(eye_r, erx - ew, ery - ew, erx + ew, ery + ew)
            canvas.itemconfig(eye_l_shine, state='normal')
            canvas.itemconfig(eye_r_shine, state='normal')
            canvas.coords(eye_l_shine, elx, ely - 3, elx + 3, ely)
            canvas.coords(eye_r_shine, erx, ery - 3, erx + 3, ery)

            if ai_state == "THINKING":
                canvas.itemconfig(status_text, text=f"Thinking{dots}", fill='#ffffaa')
                canvas.itemconfig(pill, outline='#ffff55')
                canvas.itemconfig(eye_l, fill='#ffff55')
                canvas.itemconfig(eye_r, fill='#ffff55')
            elif ai_state == "GRAPHIFY":
                canvas.itemconfig(status_text, text=f"Team Sync{dots}", fill='#e879f9')
                canvas.itemconfig(pill, outline='#c026d3')
                # Make the eyes look connected (wide)
                canvas.coords(eye_l, sx+15, sy+28, sx+35, sy+38)
                canvas.coords(eye_r, sx+45, sy+28, sx+65, sy+38)
                canvas.itemconfig(eye_l, fill='#e879f9')
                canvas.itemconfig(eye_r, fill='#e879f9')
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
            blink_phase = anim_frame % 30
            if blink_phase == 0 or blink_phase == 1:
                canvas.coords(eye_l, sx + 22, sy + 32, sx + 32, sy + 34)
                canvas.coords(eye_r, sx + 48, sy + 32, sx + 58, sy + 34)
                canvas.itemconfig(eye_l_shine, state='hidden')
                canvas.itemconfig(eye_r_shine, state='hidden')
            else:
                canvas.coords(eye_l, sx + 22, sy + 28, sx + 32, sy + 38)
                canvas.coords(eye_r, sx + 48, sy + 28, sx + 58, sy + 38)
                canvas.itemconfig(eye_l_shine, state='normal')
                canvas.itemconfig(eye_r_shine, state='normal')

                cycle = anim_frame % 80
                px_offset, py_offset = 0, 0
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

                el_cx, el_cy = sx + 27, sy + 33
                er_cx, er_cy = sx + 53, sy + 33
                canvas.coords(eye_l_shine, el_cx + px_offset - 1.5, el_cy + py_offset - 1.5, el_cx + px_offset + 1.5, el_cy + py_offset + 1.5)
                canvas.coords(eye_r_shine, er_cx + px_offset - 1.5, er_cy + py_offset - 1.5, er_cx + px_offset + 1.5, er_cy + py_offset + 1.5)

    elif dashboard_active and anim_frame % 10 == 0:
        # Don't refresh Settings section — it's widget-based and self-managed.
        # Refreshing it would destroy all typed API keys every 18 seconds.
        if current_section != 'Settings':
            refresh_dashboard_content()

    root.after(150, animation_loop)

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
        backend_status = "Active"
        if dashboard_active: refresh_dashboard_content()
        return
    if "STATUS: BACKEND:OFFLINE" in line:
        backend_status = "Offline"
        if dashboard_active: refresh_dashboard_content()
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
        if "web_search" in tool or "search" in tool:
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
if 'graphify_nodes' not in globals():
    graphify_nodes = [
        {"id": "node1", "role": "Researcher", "model": "llama3-8b\n(Ollama)", "x": 60, "y": 200, "color": "#2563EB", "outline": "#60A5FA", "r": 20},
        {"id": "node2", "role": "Orchestrator", "model": "llama3-70b\n(Groq)", "x": 400, "y": 200, "color": "#7C3AED", "outline": "#A78BFA", "r": 25},
        {"id": "node3", "role": "Reviewer", "model": "gemma-2b\n(Ollama)", "x": 740, "y": 200, "color": "#10B981", "outline": "#34D399", "r": 20}
    ]
    drag_data = {"node_idx": -1, "last_x": 0, "last_y": 0}

def _draw_teams_section(dc, w, h):
    dc.delete('team_element')
    
    # Header
    dc.create_text(24, 30, text='Graphify Teams (Multi-Model Collaboration)', fill='#E5E7EB', font=('Segoe UI', 16, 'bold'), anchor='w', tags='team_element')
    dc.create_text(24, 55, text='Drag and drop nodes to organize your chain. Edit or create new teams below.', fill='#9CA3AF', font=('Segoe UI', 10), anchor='w', tags='team_element')
    
    # Background Box
    dc.create_rectangle(20, 80, w - 20, 320, fill='#1A1D23', outline='#374151', width=1, tags='team_element')
    
    # Draw connections (lines)
    for i in range(len(graphify_nodes) - 1):
        n1 = graphify_nodes[i]
        n2 = graphify_nodes[i+1]
        dc.create_line(n1['x'], n1['y'], n2['x'], n2['y'], fill='#4F46E5', width=3, dash=(4,4), tags='team_element')
        
    # Draw nodes
    for i, n in enumerate(graphify_nodes):
        x, y, r = n['x'], n['y'], n['r']
        tag = f'node_{i}'
        # Node Oval
        dc.create_oval(x-r, y-r, x+r, y+r, fill=n['color'], outline=n['outline'], width=2, tags=('team_element', tag, 'draggable'))
        # Number inside
        dc.create_text(x, y, text=str(i+1), fill='white', font=('Segoe UI', max(10, r-8), 'bold'), tags=('team_element', tag, 'draggable'))
        # Role Label
        dc.create_text(x, y - r - 15, text=n['role'], fill='#D1D5DB', font=('Segoe UI', 10, 'bold'), tags=('team_element', tag, 'draggable'))
        # Model Label
        dc.create_text(x, y + r + 15, text=n['model'], fill='#9CA3AF', font=('Segoe UI', 9), justify='center', tags=('team_element', tag, 'draggable'))
        
    # Button: New Team
    dc.create_rectangle(24, 340, 140, 375, fill='#4F46E5', outline='', tags=('team_element', 'btn_add_team'))
    dc.create_text(82, 357, text='+ New Team', fill='white', font=('Segoe UI', 10, 'bold'), tags=('team_element', 'btn_add_team'))
    
    # Button: Edit Models
    dc.create_rectangle(150, 340, 270, 375, fill='#374151', outline='', tags=('team_element', 'btn_edit_team'))
    dc.create_text(210, 357, text='Edit Models', fill='white', font=('Segoe UI', 10, 'bold'), tags=('team_element', 'btn_edit_team'))

    # --- Interaction Logic ---
    
    def on_drag_start(e):
        items = dc.find_withtag("current")
        if not items: return
        tags = dc.gettags(items[0])
        for tag in tags:
            if tag.startswith('node_'):
                idx = int(tag.split('_')[1])
                drag_data['node_idx'] = idx
                drag_data['last_x'] = e.x
                drag_data['last_y'] = e.y
                break

    def on_drag_motion(e):
        idx = drag_data['node_idx']
        if idx >= 0 and idx < len(graphify_nodes):
            dx = e.x - drag_data['last_x']
            dy = e.y - drag_data['last_y']
            
            # Constrain to bounding box
            new_x = min(max(graphify_nodes[idx]['x'] + dx, 40), w - 40)
            new_y = min(max(graphify_nodes[idx]['y'] + dy, 120), 280)
            
            graphify_nodes[idx]['x'] = new_x
            graphify_nodes[idx]['y'] = new_y
            
            drag_data['last_x'] = e.x
            drag_data['last_y'] = e.y
            
            # Fast redraw just the team section
            _draw_teams_section(dc, w, h)

    def on_drag_stop(e):
        drag_data['node_idx'] = -1
        
    dc.tag_bind('draggable', '<ButtonPress-1>', on_drag_start)
    dc.tag_bind('draggable', '<B1-Motion>', on_drag_motion)
    dc.tag_bind('draggable', '<ButtonRelease-1>', on_drag_stop)
    dc.tag_bind('draggable', '<Enter>', lambda e: dc.config(cursor='hand2'))
    dc.tag_bind('draggable', '<Leave>', lambda e: dc.config(cursor=''))

    # Popup Editor
    def on_edit_team(e):
        top = tk.Toplevel()
        top.title("Edit Graphify Team")
        top.geometry("450x350")
        top.configure(bg='#0F1115')
        top.attributes('-topmost', True)
        
        tk.Label(top, text="Configure Model Chain", bg='#0F1115', fg='white', font=('Segoe UI', 14, 'bold')).pack(pady=10)
        
        frame = tk.Frame(top, bg='#0F1115')
        frame.pack(fill='both', expand=True, padx=20)
        
        entries = []
        for i, n in enumerate(graphify_nodes):
            row = tk.Frame(frame, bg='#0F1115')
            row.pack(fill='x', pady=5)
            tk.Label(row, text=f"Node {i+1} Role:", bg='#0F1115', fg='#D1D5DB').pack(side='left')
            role_entry = tk.Entry(row, width=15, bg='#1A1D23', fg='white', insertbackground='white')
            role_entry.insert(0, n['role'])
            role_entry.pack(side='left', padx=5)
            
            tk.Label(row, text="Model:", bg='#0F1115', fg='#D1D5DB').pack(side='left')
            model_entry = tk.Entry(row, width=20, bg='#1A1D23', fg='white', insertbackground='white')
            model_entry.insert(0, n['model'].replace('\n', ' '))
            model_entry.pack(side='left', padx=5)
            entries.append((role_entry, model_entry))
            
        def save_changes():
            for i, (r_ent, m_ent) in enumerate(entries):
                graphify_nodes[i]['role'] = r_ent.get()
                graphify_nodes[i]['model'] = m_ent.get().replace(' ', '\n', 1)
            _draw_teams_section(dc, w, h)
            top.destroy()
            
        tk.Button(top, text="Save & Update", command=save_changes, bg='#10B981', fg='white', relief='flat').pack(pady=15)
        
    def on_new_team(e):
        # Reset to a fresh blank team
        global graphify_nodes
        graphify_nodes = [
            {"id": "node1", "role": "Analyzer", "model": "gemma-2b\n(Ollama)", "x": 100, "y": 200, "color": "#F59E0B", "outline": "#FCD34D", "r": 20},
            {"id": "node2", "role": "Writer", "model": "llama3-8b\n(Groq)", "x": w//2, "y": 200, "color": "#3B82F6", "outline": "#93C5FD", "r": 20},
        ]
        _draw_teams_section(dc, w, h)

    # Bind buttons
    dc.tag_bind('btn_edit_team', '<Enter>', lambda e: dc.config(cursor='hand2'))
    dc.tag_bind('btn_edit_team', '<Leave>', lambda e: dc.config(cursor=''))
    dc.tag_bind('btn_edit_team', '<Button-1>', on_edit_team)
    
    dc.tag_bind('btn_add_team', '<Enter>', lambda e: dc.config(cursor='hand2'))
    dc.tag_bind('btn_add_team', '<Leave>', lambda e: dc.config(cursor=''))
    dc.tag_bind('btn_add_team', '<Button-1>', on_new_team)

root.mainloop()


