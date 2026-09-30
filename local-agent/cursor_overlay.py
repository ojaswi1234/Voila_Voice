"""cursor_overlay.py - AI cursor overlay window for Voila.

Single-agent mode (default): behaves exactly as before.
Graphify multi-agent mode: launched with --port, --name, --color-* args.

Features a buttery-smooth, static full-virtual-screen overlay with a 
tapering comet/rocket-smoke tail using segmented round-capped lines.
"""
import sys
import argparse
import tkinter as tk
import ctypes
from ctypes import wintypes
import socket
import threading
import traceback
import time
import math

def log(msg):
    try:
        with open("cursor_debug.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] [OVERLAY] {msg}\n")
    except Exception:
        pass

def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--port",          type=int, default=19882)
    parser.add_argument("--name",          type=str, default="AI")
    parser.add_argument("--color-fill",    type=str, default="#6b21a8", dest="color_fill")
    parser.add_argument("--color-outline", type=str, default="#c084fc", dest="color_outline")
    parser.add_argument("--color-glow",    type=str, default="#9333ea", dest="color_glow")
    parser.add_argument("--color-badge",   type=str, default="#4c1d95", dest="color_badge")
    parser.add_argument("--color-text",    type=str, default="#fefefe", dest="color_text")
    args, _ = parser.parse_known_args()
    return args

class CursorOverlay:
    def __init__(self):
        cfg = parse_args()
        self.cfg = cfg
        self.port = cfg.port

        log(f"Starting overlay: port={cfg.port} name={cfg.name} fill={cfg.color_fill}")
        # FORCE DPI AWARENESS so Tkinter coordinates match physical pixels!
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        self.root = tk.Tk()

        self.root.title(f"Voila AI Cursor [{cfg.name}]")
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "white")
        self.root.overrideredirect(True)
        self.root.config(bg="white")

        self.root.update_idletasks()
        self.hwnd = int(self.root.frame(), 16)

        user32 = ctypes.windll.user32
        
        # Setup proper argtypes for 64-bit safety
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]

        if sys.maxsize > 2**32:
            user32.GetWindowLongPtrW.restype = ctypes.c_void_p
            user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            GetWindowLong = user32.GetWindowLongPtrW
            SetWindowLong = user32.SetWindowLongPtrW
        else:
            GetWindowLong = user32.GetWindowLongW
            SetWindowLong = user32.SetWindowLongW

        try:
            style = GetWindowLong(self.hwnd, -20)
            SetWindowLong(self.hwnd, -20, style | 0x00080000 | 0x00000020)
            log("Applied click-through styles successfully.")
        except Exception as e:
            log(f"Failed to apply click-through styles: {e}")

        # Get Full Virtual Screen Size (Multi-Monitor Support)
        SM_XVIRTUALSCREEN = 76
        SM_YVIRTUALSCREEN = 77
        SM_CXVIRTUALSCREEN = 78
        SM_CYVIRTUALSCREEN = 79
        
        self.VX = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self.VY = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self.VW = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        self.VH = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        
        # Fallback if virtual screen metrics fail
        if self.VW == 0 or self.VH == 0:
            self.VX, self.VY = 0, 0
            self.VW, self.VH = self.root.winfo_screenwidth(), self.root.winfo_screenheight()

        self.root.geometry(f"{self.VW}x{self.VH}+{self.VX}+{self.VY}")

        self.canvas = tk.Canvas(self.root, width=self.VW, height=self.VH, bg="white", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # --- Trail configuration ---
        self.trail_len = 20 # Number of segments for the rocket smoke / light wave tail
        self.history = []
        
        self.trail_outer = []
        self.trail_inner = []
        for i in range(self.trail_len):
            progress = i / float(self.trail_len)
            width_outer = 6.0 * (1.0 - math.pow(progress, 0.6))
            width_inner = 3.0 * (1.0 - math.pow(progress, 0.6))
            if width_outer < 0.5: width_outer = 0
            if width_inner < 0.5: width_inner = 0

            # Segmented tapering line
            o = self.canvas.create_line(-99999, -99999, -99999, -99999, fill=cfg.color_outline, width=width_outer, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            i_c = self.canvas.create_line(-99999, -99999, -99999, -99999, fill=cfg.color_glow, width=width_inner, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            self.trail_outer.append(o)
            self.trail_inner.append(i_c)

        # --- Draw cursor head ---
        arrow_pts = [
            0, 0,
            0, 15,
            4, 12,
            8, 19,
            10, 18,
            6, 11,
            11, 11,
        ]
        self.head_outer = self.canvas.create_polygon(*arrow_pts, fill="", outline=cfg.color_outline, width=3, joinstyle=tk.ROUND)
        self.head_glow = self.canvas.create_polygon(*arrow_pts, fill="", outline=cfg.color_glow, width=2, joinstyle=tk.ROUND)
        self.head_fill = self.canvas.create_polygon(*arrow_pts, fill=cfg.color_fill, outline=cfg.color_text, width=1.0, joinstyle=tk.MITER)

        # --- Draw badge ---
        px, py = 14, 9
        pw, ph = 18, 10
        self.badge_items = []
        self.badge_items.append(self.canvas.create_oval(px - 1, py - 1, px + ph + 1, py + ph + 1, fill="", outline=cfg.color_glow, width=2))
        self.badge_items.append(self.canvas.create_oval(px + pw - ph - 1, py - 1, px + pw + 1, py + ph + 1, fill="", outline=cfg.color_glow, width=2))
        self.badge_items.append(self.canvas.create_oval(px, py, px + ph, py + ph, fill=cfg.color_badge, outline=cfg.color_text, width=1.0))
        self.badge_items.append(self.canvas.create_oval(px + pw - ph, py, px + pw, py + ph, fill=cfg.color_badge, outline=cfg.color_text, width=1.0))
        self.badge_items.append(self.canvas.create_rectangle(px + ph/2, py, px + pw - ph/2, py + ph, fill=cfg.color_badge, outline=""))
        self.badge_items.append(self.canvas.create_line(px + ph/2, py, px + pw - ph/2, py, fill=cfg.color_text, width=1.0))
        self.badge_items.append(self.canvas.create_line(px + ph/2, py + ph, px + pw - ph/2, py + ph, fill=cfg.color_text, width=1.0))
        
        label = cfg.name[:4] if len(cfg.name) > 4 else cfg.name
        self.badge_text = self.canvas.create_text(px + pw/2, py + ph/2, text=label, fill=cfg.color_text, font=("Segoe UI", 5, "bold"))

        self.target_x = -9999
        self.target_y = -9999
        self.is_visible = False
        
        # Advanced Animation Properties
        self.is_spawning = False
        self.spawn_progress = 0.0
        self.is_homing = False
        self.home_progress = 0.0
        self.home_x = 0
        self.home_y = 0
        self.home_start_x = 0
        self.home_start_y = 0

        # Move window to virtual screen origin permanently
        ctypes.windll.user32.SetWindowPos(self.hwnd, -1, self.VX, self.VY, 0, 0, 0x0001 | 0x0010 | 0x0040)

        # UDP Thread
        t = threading.Thread(target=self.listen_udp, daemon=True)
        t.start()

        # Start animation loop (approx 60fps)
        self.update_frame()
        self.root.mainloop()

    def listen_udp(self):
        log(f"UDP Thread starting on port {self.port}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", self.port))
            log(f"Bound to 127.0.0.1:{self.port} successfully.")
        except Exception as e:
            log(f"CRITICAL: Failed to bind UDP socket on port {self.port}! {e}\n{traceback.format_exc()}")
            return

        while True:
            try:
                data, _ = sock.recvfrom(64)
                if data == b"HIDE":
                    self.target_x = -99999
                    self.target_y = -99999
                    continue
                if data.startswith(b"SPAWN,"):
                    parts = data.decode("utf-8").split(",")
                    self.target_x = int(float(parts[1]))
                    self.target_y = int(float(parts[2]))
                    self.is_spawning = True
                    self.spawn_progress = 0.0
                    self.is_homing = False
                    continue
                if data.startswith(b"HOME,"):
                    parts = data.decode("utf-8").split(",")
                    self.home_x = int(float(parts[1]))
                    self.home_y = int(float(parts[2]))
                    self.home_start_x = self.target_x
                    self.home_start_y = self.target_y
                    self.is_homing = True
                    self.home_progress = 0.0
                    self.is_spawning = False
                    continue
                parts = data.decode("utf-8").split(",")
                if len(parts) == 2:
                    self.target_x, self.target_y = int(float(parts[0])), int(float(parts[1]))
                    self.is_homing = False
            except Exception as e:
                log(f"UDP Loop Error: {e}")

    def update_frame(self):
        try:
            scale = 1.0
            angle = 0.0
            show_tail = True
            base_x, base_y = self.target_x, self.target_y

            if self.is_spawning:
                self.spawn_progress += 0.03
                if self.spawn_progress >= 1.0:
                    self.is_spawning = False
                else:
                    t = self.spawn_progress
                    jump_offset = math.sin(t * math.pi) * 70
                    base_y = self.target_y - jump_offset
                    scale = t
                    show_tail = False
            elif self.is_homing:
                self.home_progress += 0.02
                if self.home_progress >= 1.0:
                    self.is_homing = False
                    self.target_x = -99999
                    self.target_y = -99999
                    base_x, base_y = -99999, -99999
                else:
                    t = self.home_progress
                    if t < 0.6:
                        et = t / 0.6
                        ease = 2 * et * et if et < 0.5 else 1 - math.pow(-2 * et + 2, 2) / 2
                        base_x = self.home_start_x + (self.home_x - self.home_start_x) * ease
                        base_y = self.home_start_y + (self.home_y - self.home_start_y) * ease
                    else:
                        jt = (t - 0.6) / 0.4
                        base_x = self.home_x
                        jump_offset = math.sin(jt * math.pi) * 70
                        base_y = self.home_y - jump_offset
                        angle = jt * 360 * 2
                        scale = 1.0 - jt
                        show_tail = False

            if base_x <= -9999 or base_y <= -9999:
                if self.is_visible:
                    self.is_visible = False
                    self.history = []
                    for i in range(self.trail_len):
                        self.canvas.coords(self.trail_outer[i], -99999, -99999, -99999, -99999)
                        self.canvas.coords(self.trail_inner[i], -99999, -99999, -99999, -99999)
                    self.move_head_to(-99999, -99999, 1.0, 0.0)
            else:
                if not self.is_visible:
                    self.is_visible = True

                canvas_tx = base_x - self.VX
                canvas_ty = base_y - self.VY

                # Insert current position into history
                # We start the tail from the BASE of the cursor (approx +3, +10)
                tail_base_x = canvas_tx + 3
                tail_base_y = canvas_ty + 10

                if not self.history:
                    self.history = [(tail_base_x, tail_base_y)] * (self.trail_len + 1)
                else:
                    self.history.insert(0, (tail_base_x, tail_base_y))
                    if len(self.history) > self.trail_len + 1:
                        self.history = self.history[:self.trail_len + 1]

                # Update Cursor Head Graphics
                self.move_head_to(canvas_tx, canvas_ty, scale, angle)

                # Update Trail Segments (Smooth light wave / smoke rocket tail)
                for i in range(self.trail_len):
                    if i + 1 < len(self.history):
                        p1x, p1y = self.history[i]
                        p2x, p2y = self.history[i+1]
                        
                        if show_tail:
                            self.canvas.coords(self.trail_outer[i], p1x, p1y, p2x, p2y)
                            self.canvas.coords(self.trail_inner[i], p1x, p1y, p2x, p2y)
                        else:
                            self.canvas.coords(self.trail_outer[i], -99999, -99999, -99999, -99999)
                            self.canvas.coords(self.trail_inner[i], -99999, -99999, -99999, -99999)
                    else:
                        self.canvas.coords(self.trail_outer[i], -99999, -99999, -99999, -99999)
                        self.canvas.coords(self.trail_inner[i], -99999, -99999, -99999, -99999)
                        self.canvas.coords(self.trail_outer[i], -99999, -99999, -99999, -99999)
                        self.canvas.coords(self.trail_inner[i], -99999, -99999, -99999, -99999)
        except Exception as e:
            log(f"Animation loop error: {e}")

        # Run at ~60 FPS
        self.root.after(16, self.update_frame)

    def _transform(self, pts, cx, cy, scale, angle):
        import math
        out = []
        rad = math.radians(angle)
        # 3D spin simulation: X scale flips with cosine of angle!
        cos_spin = math.cos(rad)
        
        for i in range(0, len(pts), 2):
            x = pts[i] - cx
            y = pts[i+1] - cy
            # Apply 3D coin-flip spin on X axis, plus overall scale
            nx = (x * cos_spin) * scale
            ny = y * scale
            out.extend([nx + cx, ny + cy])
        return out

    def move_head_to(self, cx, cy, scale, angle):
        arrow_pts = [
            cx, cy,
            cx, cy + 15,
            cx + 4, cy + 12,
            cx + 8, cy + 19,
            cx + 10, cy + 18,
            cx + 6, cy + 11,
            cx + 11, cy + 11,
        ]
        arrow_pts = self._transform(arrow_pts, cx, cy, scale, angle)
        self.canvas.coords(self.head_outer, *arrow_pts)
        self.canvas.coords(self.head_glow, *arrow_pts)
        self.canvas.coords(self.head_fill, *arrow_pts)

        px, py = cx + 14, cy + 9
        pw, ph = 18, 10
        badge_pts = [
            # Each list is a bounding box, we transform the center and scale the size
            # But wait, bounding box can't rotate natively. We can just scale/offset it if it doesn't spin,
            # or we can just hide the badge during scale/spin. Let's hide it during spawn/home.
        ]
        
        if scale < 0.95 or angle > 0:
            for item in self.badge_items:
                self.canvas.coords(item, -99999, -99999, -99999, -99999)
            self.canvas.coords(self.badge_text, -99999, -99999)
        else:
            self.canvas.coords(self.badge_items[0], px - 1, py - 1, px + ph + 1, py + ph + 1)
            self.canvas.coords(self.badge_items[1], px + pw - ph - 1, py - 1, px + pw + 1, py + ph + 1)
            self.canvas.coords(self.badge_items[2], px, py, px + ph, py + ph)
            self.canvas.coords(self.badge_items[3], px + pw - ph, py, px + pw, py + ph)
            self.canvas.coords(self.badge_items[4], px + ph/2, py, px + pw - ph/2, py + ph)
            self.canvas.coords(self.badge_items[5], px + ph/2, py, px + pw - ph/2, py)
            self.canvas.coords(self.badge_items[6], px + ph/2, py + ph, px + pw - ph/2, py + ph)
            self.canvas.coords(self.badge_text, px + pw/2, py + ph/2)

def create_overlay():
    CursorOverlay()

if __name__ == "__main__":
    create_overlay()
