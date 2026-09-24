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
    hwnd = 0
    import ctypes
    root.update_idletasks() # ensure window exists
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = root.winfo_id()
        # WS_EX_LAYERED | WS_EX_TRANSPARENT
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)
    except Exception:
        hwnd = root.winfo_id()

    canvas = tk.Canvas(root, width=80, height=80, bg="white", highlightthickness=0)
    canvas.pack()
    
    # Ultra-Cool Neon Purple AI Cursor Design
    cx, cy = 16, 16
    
    # Scaled down sleek arrow coordinates
    arrow_pts = [
        cx, cy,
        cx, cy + 24,
        cx + 6, cy + 19,
        cx + 12, cy + 30,
        cx + 16, cy + 28,
        cx + 10, cy + 17,
        cx + 18, cy + 17
    ]
    
    # 1. Neon Glow Layers (Multiple outlines for a glow effect)
    canvas.create_polygon(*arrow_pts, fill="", outline="#c084fc", width=5, joinstyle=tk.ROUND) # Soft outer purple glow
    canvas.create_polygon(*arrow_pts, fill="", outline="#9333ea", width=3, joinstyle=tk.ROUND) # Stronger inner glow
    
    # 2. Main Arrow Body (Deep purple with a stark white edge for crispness)
    canvas.create_polygon(*arrow_pts, fill="#6b21a8", outline="#fefefe", width=1.5, joinstyle=tk.MITER)
    
    # 3. Floating AI Pill Badge
    px, py = cx + 22, cy + 14
    pw, ph = 24, 14
    
    # Pill Glow
    canvas.create_oval(px - 1, py - 1, px + ph + 1, py + ph + 1, fill="", outline="#a855f7", width=3)
    canvas.create_oval(px + pw - ph - 1, py - 1, px + pw + 1, py + ph + 1, fill="", outline="#a855f7", width=3)
    
    # Pill Body
    canvas.create_oval(px, py, px + ph, py + ph, fill="#4c1d95", outline="#fefefe", width=1.2)
    canvas.create_oval(px + pw - ph, py, px + pw, py + ph, fill="#4c1d95", outline="#fefefe", width=1.2)
    canvas.create_rectangle(px + ph/2, py, px + pw - ph/2, py + ph, fill="#4c1d95", outline="")
    
    # Redraw top/bottom edges of rectangle for clean border
    canvas.create_line(px + ph/2, py, px + pw - ph/2, py, fill="#fefefe", width=1.2)
    canvas.create_line(px + ph/2, py + ph, px + pw - ph/2, py + ph, fill="#fefefe", width=1.2)
    
    # AI Text
    canvas.create_text(px + pw/2, py + ph/2, text="AI", fill="#fefefe", font=("Segoe UI", 7, "bold"))

    # Place window initially off-screen
    root.geometry(f"80x80+-100+-100")
    
    import socket
    import threading

    def listen_udp(target_hwnd):
        import ctypes
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 19882))
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        HWND_TOPMOST = -1
        while True:
            try:
                data, _ = sock.recvfrom(64)
                if data == b"HIDE":
                    ctypes.windll.user32.SetWindowPos(target_hwnd, HWND_TOPMOST, -9999, -9999, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
                    continue
                parts = data.decode("utf-8").split(",")
                if len(parts) == 2:
                    x, y = int(float(parts[0])), int(float(parts[1]))
                    # Offset by 16 because cx, cy = 16, 16
                    ctypes.windll.user32.SetWindowPos(target_hwnd, HWND_TOPMOST, x - 16, y - 16, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
            except Exception:
                pass

    t = threading.Thread(target=listen_udp, args=(hwnd,), daemon=True)
    t.start()
    
    root.mainloop()

if __name__ == "__main__":
    create_overlay()
