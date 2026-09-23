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
    
    # Premium Cyberpunk AI Cursor Design
    cx, cy = 16, 16
    
    T = (cx, cy)
    L = (cx, cy + 40)
    I = (cx + 12, cy + 30)
    RT = (cx + 26, cy + 54)
    R = (cx + 34, cy + 32)
    C = (cx + 10, cy + 24)
    
    # 1. 3D Beveled Facets (Dark Hacker Theme)
    canvas.create_polygon(*T, *L, *I, *C, fill="#2C313A", outline="")
    canvas.create_polygon(*T, *C, *R, fill="#181A1F", outline="")
    canvas.create_polygon(*C, *I, *RT, *R, fill="#0D0F12", outline="")
    
    # 2. Electric Blue Glow (Right Edge)
    canvas.create_line(*T, *R, *RT, fill="#0088FF", width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
    
    # 3. Cyberpunk Crosshair at the Tip
    ch_len = 8
    canvas.create_line(cx - ch_len, cy, cx + ch_len, cy, fill="#0088FF", width=1.5)
    canvas.create_line(cx, cy - ch_len, cx, cy + ch_len, fill="#0088FF", width=1.5)
    canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#181A1F", outline="#0088FF", width=1.5)

    # 4. Electric Blue AI Pill Badge
    px, py = cx + 28, cy + 18
    pw, ph = 26, 16
    
    # Pill Shadow (Dark Drop shadow for depth)
    shadow_offset = 2
    canvas.create_oval(px + shadow_offset, py + shadow_offset, px + ph + shadow_offset, py + ph + shadow_offset, fill="#050505", outline="")
    canvas.create_oval(px + pw - ph + shadow_offset, py + shadow_offset, px + pw + shadow_offset, py + ph + shadow_offset, fill="#050505", outline="")
    canvas.create_rectangle(px + ph/2 + shadow_offset, py + shadow_offset, px + pw - ph/2 + shadow_offset, py + ph + shadow_offset, fill="#050505", outline="")
    
    # Pill Body
    canvas.create_oval(px, py, px + ph, py + ph, fill="#181A1F", outline="#0088FF", width=1.5)
    canvas.create_oval(px + pw - ph, py, px + pw, py + ph, fill="#181A1F", outline="#0088FF", width=1.5)
    canvas.create_rectangle(px + ph/2, py, px + pw - ph/2, py + ph, fill="#181A1F", outline="")
    # Redraw top/bottom edges of rectangle
    canvas.create_line(px + ph/2, py, px + pw - ph/2, py, fill="#0088FF", width=1.5)
    canvas.create_line(px + ph/2, py + ph, px + pw - ph/2, py + ph, fill="#0088FF", width=1.5)
    
    # AI Text
    canvas.create_text(px + pw/2, py + ph/2, text="AI", fill="#00AAFF", font=("Segoe UI", 8, "bold"))

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
                    # Offset by 16 because cx, cy = 16, 16
                    root.after(0, lambda x=x, y=y: root.geometry(f"80x80+{x-16}+{y-16}"))
            except Exception:
                pass

    t = threading.Thread(target=listen_udp, daemon=True)
    t.start()
    
    root.mainloop()

if __name__ == "__main__":
    create_overlay()
