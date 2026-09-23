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

    canvas = tk.Canvas(root, width=32, height=32, bg="white", highlightthickness=0)
    canvas.pack()
    
    # Draw AI Cursor (Purple arrow)
    cx, cy = 0, 0
    # Match the desktop face icon we added to run_hidden_agent
    canvas.create_polygon(cx+2, cy+2, cx+2, cy+22, cx+8, cy+17, cx+12, cy+25, cx+15, cy+24, cx+11, cy+15, cx+17, cy+15, fill="#a78bfa", outline="#7c3aed", width=1.5)
    canvas.create_oval(cx+15, cy+22, cx+20, cy+27, fill="#a78bfa", outline="")
    # AI Label
    canvas.create_text(cx+23, cy+15, text="AI", fill="#7c3aed", font=("Segoe UI", 8, "bold"), anchor="w")

    # Place window initially off-screen
    root.geometry(f"48x32+-100+-100")
    
    import socket
    import threading

    def listen_udp():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 19882))
        while True:
            try:
                data, _ = sock.recvfrom(64)
                if data == b"HIDE":
                    root.after(0, lambda: root.geometry(f"48x32+-100+-100"))
                    continue
                parts = data.decode("utf-8").split(",")
                if len(parts) == 2:
                    x, y = int(float(parts[0])), int(float(parts[1]))
                    # Offset slightly so the tip of the arrow is at x,y
                    root.after(0, lambda x=x, y=y: root.geometry(f"48x32+{x}+{y}"))
            except Exception:
                pass

    t = threading.Thread(target=listen_udp, daemon=True)
    t.start()
    
    root.mainloop()

if __name__ == "__main__":
    create_overlay()
