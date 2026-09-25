import math
import time
import os
import sys
import ctypes

# Add local-agent to path so we can import cursor_motion
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "local-agent"))
import cursor_motion

w = ctypes.windll.user32.GetSystemMetrics(0)
h = ctypes.windll.user32.GetSystemMetrics(1)

def draw_spring(start_x, start_y, end_x, end_y, loops=6, radius=100, points_per_loop=24):
    total_points = loops * points_per_loop
    dx = end_x - start_x
    dy = end_y - start_y
    angle = math.atan2(dy, dx)
    
    for i in range(total_points + 1):
        t = i / total_points
        base_x = start_x + dx * t
        base_y = start_y + dy * t
        
        theta = i * (2 * math.pi / points_per_loop)
        
        perp_x = -math.sin(angle)
        perp_y = math.cos(angle)
        par_x = math.cos(angle)
        par_y = math.sin(angle)
        
        off_x = radius * math.cos(theta) * par_x + radius * math.sin(theta) * perp_x
        off_y = radius * math.cos(theta) * par_y + radius * math.sin(theta) * perp_y
        
        nx = base_x + off_x
        ny = base_y + off_y
        
        # Bypass humanizer and send UDP packet instantly
        cursor_motion._set_cursor_pos(int(nx), int(ny))
        time.sleep(0.008) # 8ms = ~120fps

print("Drawing spirals...")

# 1. Top right to bottom left
draw_spring(w-150, 150, 150, h-150)
# 2. Top left to bottom right
draw_spring(150, 150, w-150, h-150)
# 3. Bottom right to top left
draw_spring(w-150, h-150, 150, 150)
# 4. Bottom left to top right
draw_spring(150, h-150, w-150, 150)

print("Done drawing spirals!")
