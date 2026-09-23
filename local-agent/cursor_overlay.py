import sys
import tkinter as tk

def create_overlay():
    root = tk.Tk()
    root.title("Voila AI Cursor")
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", "white")
    root.overrideredirect(True)
    root.config(bg="white")
    
    # Optional: Make click-through
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        # WS_EX_LAYERED | WS_EX_TRANSPARENT
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)
    except Exception:
        pass

    canvas = tk.Canvas(root, width=80, height=80, bg="white", highlightthickness=0)
    canvas.pack()
    
    # Premium AI Cursor Design
    cx, cy = 2, 2
    
    # Sleek arrow coordinates
    arrow_pts = [
        cx, cy,
        cx, cy + 24,
        cx + 5, cy + 18,
        cx + 11, cy + 28,
        cx + 15, cy + 26,
        cx + 9, cy + 16,
        cx + 17, cy + 16
    ]
    
    # 1. Drop shadow (dark gray, slightly offset)
    shadow_offset = 2
    shadow_pts = [p + shadow_offset for p in arrow_pts]
    canvas.create_polygon(*shadow_pts, fill="#2a2a2a", outline="")
    
    # 2. Main Arrow Body (Emerald Green with almost-white border to avoid transparency clipping)
    canvas.create_polygon(*arrow_pts, fill="#10B981", outline="#FEFEFE", width=2, joinstyle=tk.MITER)
    
    # 3. AI Pill Badge
    px, py = cx + 20, cy + 14
    pw, ph = 26, 16
    
    # Pill Shadow
    canvas.create_oval(px + shadow_offset, py + shadow_offset, px + ph + shadow_offset, py + ph + shadow_offset, fill="#2a2a2a", outline="")
    canvas.create_oval(px + pw - ph + shadow_offset, py + shadow_offset, px + pw + shadow_offset, py + ph + shadow_offset, fill="#2a2a2a", outline="")
    canvas.create_rectangle(px + ph/2 + shadow_offset, py + shadow_offset, px + pw - ph/2 + shadow_offset, py + ph + shadow_offset, fill="#2a2a2a", outline="")
    
    # Pill Body
    canvas.create_oval(px, py, px + ph, py + ph, fill="#10B981", outline="#FEFEFE", width=1.5)
    canvas.create_oval(px + pw - ph, py, px + pw, py + ph, fill="#10B981", outline="#FEFEFE", width=1.5)
    canvas.create_rectangle(px + ph/2, py, px + pw - ph/2, py + ph, fill="#10B981", outline="")
    # Redraw top/bottom lines of the pill so they have borders
    canvas.create_line(px + ph/2, py, px + pw - ph/2, py, fill="#FEFEFE", width=1.5)
    canvas.create_line(px + ph/2, py + ph, px + pw - ph/2, py + ph, fill="#FEFEFE", width=1.5)
    
    # AI Text
    canvas.create_text(px + pw/2, py + ph/2, text="AI", fill="#FEFEFE", font=("Segoe UI", 8, "bold"))

    # Place window initially off-screen
    root.geometry(f"80x80+-100+-100")
    
    import socket
    import threading

    def listen_udp():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 19882))
        while True:
            try:
                data, _ = sock.recvfrom(64)
                if data == b"HIDE":
                    root.after(0, lambda: root.geometry(f"80x80+-100+-100"))
                    continue
                parts = data.decode("utf-8").split(",")
                if len(parts) == 2:
                    x, y = int(float(parts[0])), int(float(parts[1]))
                    # Offset slightly so the tip of the arrow is at x,y (since cx,cy=2,2)
                    root.after(0, lambda x=x, y=y: root.geometry(f"80x80+{x-2}+{y-2}"))
            except Exception:
                pass

    t = threading.Thread(target=listen_udp, daemon=True)
    t.start()
    
    root.mainloop()

if __name__ == "__main__":
    create_overlay()
