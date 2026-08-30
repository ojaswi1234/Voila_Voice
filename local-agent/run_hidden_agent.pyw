import tkinter as tk
import subprocess
import threading
import sys
import time
import math
import random

# Removed psutil import completely as per user request to drop overhead
PSUTIL_AVAILABLE = False

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
snot_bubble = canvas.create_oval(0, 0, 0, 0, fill='#aaddff', outline='#ffffff', state='hidden')
zzz1 = canvas.create_text(0, 0, text="Z", fill='#aaddff', font=("Segoe UI", 12, "bold"), state='hidden')
zzz2 = canvas.create_text(0, 0, text="z", fill='#aaddff', font=("Segoe UI", 10, "bold"), state='hidden')
zzz3 = canvas.create_text(0, 0, text="z", fill='#aaddff', font=("Segoe UI", 8, "bold"), state='hidden')

face_parts = (body, arm_l, arm_r, leg1, leg2, leg3, leg4, eye_l, eye_r, eye_l_shine, eye_r_shine, snot_bubble, zzz1, zzz2, zzz3)

# Perfectly positioned Title (x=90)
title_text = canvas.create_text(90, 45, text="Voila", fill="#ffffff", font=("Segoe UI", 12, "bold"), anchor="w")

# Perfectly centered status in the cloud (x=150+55=205)
status_text = canvas.create_text(cx+55, cy+25, text="Standing by...", fill="#888888", font=("Segoe UI", 8, "italic"), anchor="center", width=150)

# Close Button - larger clickable area for better hit detection
close_btn_bg = canvas.create_oval(245, 25, 295, 65, fill="", outline="", width=0, state='hidden')
close_btn = canvas.create_text(270, 45, text="✕", fill="#888888", font=("Segoe UI", 20, "bold"), anchor="center")

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
    "peak_commands_per_min": 0
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

def refresh_dashboard_content():
    global dash_canvas
    if not dashboard_active or dash_canvas is None:
        return

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
    dc.create_text(24, 178, text='Active', fill='#10B981', font=('Segoe UI', 20, 'bold'), anchor='w')
    dc.create_text(w - 24, 178, text=f"{usage_stats['avg_latency_ms']}ms", fill='#6B7280', font=('Segoe UI', 12), anchor='e')

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
    dc.create_text(card_w + 27, 52, text='Active', fill='#10B981', font=('Segoe UI', 16, 'bold'), anchor='w')
    dc.create_text(card_w * 2 + 3, 52, text=f"{usage_stats['avg_latency_ms']}ms", fill='#6B7280', font=('Segoe UI', 10), anchor='e')

    success_rate = 0
    if usage_stats['commands_executed'] > 0:
        success_rate = int((usage_stats['commands_successful'] / usage_stats['commands_executed']) * 100)
    session_duration = int((time.time() - usage_stats['session_start']) / 60)
    commands_per_min = usage_stats['commands_executed'] // max(session_duration, 1) if session_duration > 0 else 0

    radar_y = 100
    radar_size = min(160, w // 2 - 30)
    radar_cx = radar_size // 2 + 20
    radar_cy = radar_y + radar_size // 2
    radar_r = max(30, radar_size // 2 - 16)

    dc.create_text(0, radar_y, text='Performance Radar', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    axis_values = [
        success_rate / 100.0,
        min(1.0, commands_per_min / 10.0),
        0.8, 0.9,
        min(1.0, max(0, (100 - usage_stats['avg_latency_ms']) / 100.0)),
        0.85,
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
    if heatmap_cache is None:
        heatmap_cache = []
        for _ in range(7):
            row = []
            for _ in range(5):
                intensity = random.random()
                if mobile_clients > 0:
                    intensity = random.random() * 0.8 + 0.2
                row.append(intensity)
            heatmap_cache.append(row)
    return heatmap_cache

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
        # Track usage stats (every 60 frames = ~9 seconds)
        if anim_frame % 60 == 0 and mobile_clients > 0:
            if random.random() > 0.7:
                usage_stats["commands_executed"] += 1
                if random.random() > 0.1:
                    usage_stats["commands_successful"] += 1
                else:
                    usage_stats["commands_failed"] += 1
                usage_stats["last_command_time"] = time.time()
                usage_stats["avg_latency_ms"] = random.randint(20, 150)

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
                bubble_phase = anim_frame % 16
                if bubble_phase < 8:
                    br = 2 + bubble_phase
                else:
                    br = 2 + (15 - bubble_phase)
                bx, by = sx + 40, sy + 40
                canvas.coords(snot_bubble, bx - br, by - br, bx + br, by + br)
            else:
                canvas.itemconfig(snot_bubble, state='hidden')

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

    elif dashboard_active and anim_frame % 120 == 0:
        refresh_dashboard_content()

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
            if dashboard_active:
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
        
    l = line.lower()
    if "thinking" in l: ai_state = "THINKING"
    elif "search" in l: ai_state = "SEARCH"
    elif "command" in l or "powershell" in l: ai_state = "BASH"
    elif "read" in l or "write" in l or "edit" in l: ai_state = "FILE"

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
root.mainloop()
