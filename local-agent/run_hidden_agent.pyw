import tkinter as tk
import subprocess
import threading
import sys
import time
import math

# Removed psutil import completely as per user request to drop overhead
PSUTIL_AVAILABLE = False

CREATE_NO_WINDOW = 0x08000000
# Only kill the specific voila.exe instance we'll start, not all instances
# Don't kill ngrok.exe as it might be used by other applications

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
status_text = canvas.create_text(cx+55, cy+25, text="Standing by...", fill="#888888", font=("Segoe UI", 8, "italic"), anchor="center", width=150)

# Close Button shifted right slightly to x=275
close_btn = canvas.create_text(275, 45, text="✕", fill="#888888", font=("Segoe UI", 14, "bold"), anchor="center")

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
        toggle_dashboard()  # Revert to mini popup instead of closing
    else:
        cleanup_processes()
        root.destroy()
        sys.exit(0)

# Add hover effect for dashboard toggle
def on_enter_pill(e): 
    if not dashboard_active:
        canvas.itemconfig(pill, outline='#6666ff')
def on_leave_pill(e): 
    if not dashboard_active:
        canvas.itemconfig(pill, outline='#3a3a40')

def on_enter_close(e): canvas.itemconfig(close_btn, fill="#ff5555")
def on_leave_close(e): canvas.itemconfig(close_btn, fill="#888888")

canvas.tag_bind(close_btn, '<Button-1>', on_close)
canvas.tag_bind(pill, '<Button-1>', lambda e: toggle_dashboard())  # Click AI face to toggle dashboard
canvas.tag_bind(pill, '<Enter>', on_enter_pill)
canvas.tag_bind(pill, '<Leave>', on_leave_pill)
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

# Dashboard state
dashboard_active = False
original_pos = (0, 0)  # Store original position
original_size = (300, 90)  # Store original size
usage_stats = {
    "mobile_minutes": 0,
    "backend_minutes": 0,
    "session_start": time.time(),
    "last_mobile_connect": 0,
    "last_backend_connect": 0
}

def toggle_dashboard():
    """Toggle between mini popup and dashboard mode"""
    global dashboard_active, original_pos, original_size
    
    if not dashboard_active:
        # Store current position before expanding
        original_pos = (root.winfo_x(), root.winfo_y())
        original_size = (current_width, current_height)
        dashboard_active = True
        
        # Calculate center of screen
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        center_x = (screen_width - 800) // 2  # Dashboard width: 800
        center_y = (screen_height - 500) // 2  # Dashboard height: 500
        
        # Animate to center with expansion
        animate_to_dashboard(center_x, center_y, 800, 500)
    else:
        # Animate back to original position
        animate_to_mini(original_pos[0], original_pos[1], original_size[0], original_size[1])
        dashboard_active = False

def animate_to_dashboard(target_x, target_y, target_w, target_h):
    """Smooth animation to dashboard mode"""
    global current_width, current_height, target_width, target_height, transition_progress, transition_in_progress
    
    target_width = target_w
    target_height = target_h
    transition_progress = 0.0
    transition_in_progress = True
    
    def animate_step():
        global current_width, current_height, transition_progress, transition_in_progress
        
        transition_progress += 0.08
        if transition_progress > 1.0:
            transition_progress = 1.0
        
        # Ease-out cubic for smooth motion
        ease = 1 - pow(1 - transition_progress, 3)
        
        # Interpolate position
        current_x = root.winfo_x()
        current_y = root.winfo_y()
        new_x = int(current_x + (target_x - current_x) * ease)
        new_y = int(current_y + (target_y - current_y) * ease)
        
        # Interpolate size
        new_width = int(current_width + (target_width - current_width) * ease)
        new_height = int(current_height + (target_height - current_height) * ease)
        
        root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")
        canvas.config(width=new_width, height=new_height)
        
        # Update canvas elements for dashboard
        reposition_dashboard_elements(new_width, new_height)
        
        if transition_progress < 1.0:
            root.after(16, animate_step)  # ~60fps
        else:
            transition_in_progress = False
            current_width = target_width
            current_height = target_height
            draw_dashboard()  # Draw dashboard UI
    
    animate_step()

def animate_to_mini(target_x, target_y, target_w, target_h):
    """Smooth animation back to mini popup"""
    global current_width, current_height, target_width, target_height, transition_progress, transition_in_progress
    
    target_width = target_w
    target_height = target_h
    transition_progress = 0.0
    transition_in_progress = True
    
    def animate_step():
        global current_width, current_height, transition_progress, transition_in_progress
        
        transition_progress += 0.08
        if transition_progress > 1.0:
            transition_progress = 1.0
        
        ease = 1 - pow(1 - transition_progress, 3)
        
        current_x = root.winfo_x()
        current_y = root.winfo_y()
        new_x = int(current_x + (target_x - current_x) * ease)
        new_y = int(current_y + (target_y - current_y) * ease)
        
        new_width = int(current_width + (target_width - current_width) * ease)
        new_height = int(current_height + (target_height - current_height) * ease)
        
        root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")
        canvas.config(width=new_width, height=new_height)
        
        # Restore mini popup elements
        reposition_mini_elements(new_width, new_height)
        
        if transition_progress < 1.0:
            root.after(16, animate_step)
        else:
            transition_in_progress = False
            current_width = target_width
            current_height = target_height
    
    animate_step()

def reposition_dashboard_elements(w, h):
    """Reposition elements for dashboard layout"""
    global sx, sy, cx, cy
    
    cx, cy = w // 2, h // 2
    sx, sy = 40, 40  # AI face position in dashboard (top center)
    
    # Move AI face to top center
    canvas.coords(pill, cx-150, sy-40, cx+150, sy+40)
    
    # Reposition face elements
    canvas.coords(eye_l, cx-30, sy-10, cx-10, sy+10)
    canvas.coords(eye_r, cx+10, sy-10, cx+30, sy+10)
    canvas.coords(eye_l_shine, cx-25, sy-5, cx-22, sy-2)
    canvas.coords(eye_r_shine, cx+22, sy-5, cx+25, sy-2)
    
    # Hide cloud and thought bubble in dashboard mode
    for cp in cloud_parts:
        canvas.itemconfig(cp, state='hidden')
    canvas.itemconfig(status_text, state='hidden')
    
    # Reposition close button to top right
    canvas.coords(close_btn, w-30, 20)

def reposition_mini_elements(w, h):
    """Restore mini popup element positions"""
    global sx, sy, cx, cy
    
    cx, cy = w // 2, h // 2
    sx, sy = 15, 10  # Original mini popup position
    
    # Restore pill background
    canvas.coords(pill, 10, 10, w-10, h-10)
    
    # Restore face positions
    canvas.coords(eye_l, sx+22, sy+28, sx+32, sy+38)
    canvas.coords(eye_r, sx+48, sy+28, sx+58, sy+38)
    canvas.coords(eye_l_shine, sx+27, sy+30, sx+30, sy+33)
    canvas.coords(eye_r_shine, sx+53, sy+30, sx+56, sy+33)
    
    # Restore cloud elements
    new_cx = w // 2
    new_cy = h // 2 - 10
    canvas.coords(c_dot1, new_cx-60, new_cy+15, new_cx-55, new_cy+20)
    canvas.coords(c_dot2, new_cx-40, new_cy+5, new_cx-30, new_cy+15)
    canvas.coords(c_dot3, new_cx-20, new_cy-5, new_cx-5, new_cy+10)
    canvas.coords(c_oval1, new_cx, new_cy, new_cx+40, new_cy+40)
    canvas.coords(c_oval2, new_cx+20, new_cy-10, new_cx+80, new_cy+50)
    
    # Restore status text
    canvas.itemconfig(status_text, state='normal')
    canvas.coords(status_text, new_cx-50, new_cy+55)
    
    # Restore close button
    canvas.coords(close_btn, w-25, h//2)
    
    # Show cloud elements
    for cp in cloud_parts:
        canvas.itemconfig(cp, state='normal', fill='#2a2a32')

def draw_dashboard():
    """Draw dashboard UI with usage stats and connections"""
    global mobile_clients, dashboard_active
    
    # Clear canvas for dashboard
    canvas.delete("dashboard")
    
    w, h = current_width, current_height
    cx, cy = w // 2, h // 2
    
    # Draw connection status cards
    mobile_status = "Connected" if mobile_clients > 0 else "Disconnected"
    mobile_color = "#10B981" if mobile_clients > 0 else "#EF4444"
    
    # Mobile connection card
    canvas.create_rectangle(cx-300, cy-100, cx-100, cy+50, 
                           fill="#1E1E24", outline=mobile_color, width=2, tags="dashboard")
    canvas.create_text(cx-200, cy-75, text="Mobile Device", fill="#888888", 
                    font=("Segoe UI", 10, "bold"), tags="dashboard")
    canvas.create_text(cx-200, cy-50, text=mobile_status, fill=mobile_color, 
                    font=("Segoe UI", 14, "bold"), tags="dashboard")
    
    # Backend connection card
    backend_color = "#10B981"  # Assume backend is connected for now
    canvas.create_rectangle(cx+100, cy-100, cx+300, cy+50, 
                           fill="#1E1E24", outline=backend_color, width=2, tags="dashboard")
    canvas.create_text(cx+200, cy-75, text="Backend API", fill="#888888", 
                    font=("Segoe UI", 10, "bold"), tags="dashboard")
    canvas.create_text(cx+200, cy-50, text="Connected", fill=backend_color, 
                    font=("Segoe UI", 14, "bold"), tags="dashboard")
    
    # Usage heatmap area
    canvas.create_rectangle(cx-350, cy+80, cx+350, cy+220,
                           fill="#1A1A1F", outline="#2A2A35", width=1, tags="dashboard")
    canvas.create_text(cx, cy+100, text="Daily Usage Dashboard", fill="#888888",
                    font=("Segoe UI", 12, "bold"), tags="dashboard")
    
    # Calculate usage stats
    session_duration = int((time.time() - usage_stats["session_start"]) / 60)
    canvas.create_text(cx-300, cy+130, text=f"Session Duration: {session_duration} min", 
                    fill="#AAAAAA", font=("Segoe UI", 10), tags="dashboard")
    canvas.create_text(cx-300, cy+150, text=f"Mobile Usage: {usage_stats['mobile_minutes']} min", 
                    fill="#AAAAAA", font=("Segoe UI", 10), tags="dashboard")
    canvas.create_text(cx-300, cy+170, text=f"Backend Usage: {usage_stats['backend_minutes']} min", 
                    fill="#AAAAAA", font=("Segoe UI", 10), tags="dashboard")
    
    # Draw usage bar
    total_usage = usage_stats['mobile_minutes'] + usage_stats['backend_minutes']
    bar_width = 600
    mobile_bar = int((usage_stats['mobile_minutes'] / max(total_usage, 1)) * bar_width)
    backend_bar = int((usage_stats['backend_minutes'] / max(total_usage, 1)) * bar_width)
    
    canvas.create_rectangle(cx-300, cy+195, cx+300, cy+205, fill="#2A2A35", tags="dashboard")
    canvas.create_rectangle(cx-300, cy+195, cx-300+mobile_bar, cy+205, fill="#8B5CF6", width=0, tags="dashboard")
    canvas.create_rectangle(cx-300+mobile_bar, cy+195, cx-300+mobile_bar+backend_bar, cy+205, fill="#10B981", width=0, tags="dashboard")
        
def update_size():
    """Handle size changes (keep for compatibility with existing code)"""
    if not dashboard_active:
        # Only use old transition logic when not in dashboard mode
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
    canvas.coords(pill, 10, 10, new_width-10, new_height-10)
    
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
    
    # Track usage stats (every 60 frames = ~9 seconds)
    if anim_frame % 60 == 0:
        if mobile_clients > 0:
            usage_stats["mobile_minutes"] += 1
        usage_stats["backend_minutes"] += 1  # Track backend usage continuously
    
    # Bug #5 Fix: check_resources used to be called synchronously here, which
    # caused the widget to visibly freeze ~every 4.5s while psutil scanned all
    # OS processes. Now we simply read the result that a background thread
    # continuously updates — zero blocking on the UI thread.
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
            if bubble_phase < 8: br = 2 + bubble_phase
            else: br = 2 + (15 - bubble_phase)
            bx, by = sx+40, sy+40
            canvas.coords(snot_bubble, bx-br, by-br, bx+br, by+br)
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
            
    # Refresh dashboard if active
    if dashboard_active and anim_frame % 30 == 0:  # Update every 30 frames (~0.5s)
        draw_dashboard()
    
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
