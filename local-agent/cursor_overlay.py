import sys
import tkinter as tk
import ctypes
import socket
import threading
import traceback
import time

def log(msg):
    try:
        with open("cursor_debug.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] [OVERLAY] {msg}\n")
    except Exception:
        pass

def create_overlay():
    log("Starting overlay process...")
    root = tk.Tk()
    root.title("Voila AI Cursor")
    root.attributes("-topmost", True)
    root.attributes("-transparentcolor", "white")
    root.overrideredirect(True)
    root.config(bg="white")
    
    # Get true top-level HWND safely for 64-bit Windows
    root.update_idletasks()
    hwnd = int(root.frame(), 16)
    
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    
    # Define 64-bit safe signatures
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

    log(f"Window initialized. True HWND: {hwnd}")
    
    try:
        style = GetWindowLong(hwnd, -20)
        SetWindowLong(hwnd, -20, style | 0x00080000 | 0x00000020)
        log("Applied click-through styles successfully.")
    except Exception as e:
        log(f"Failed to apply click-through styles: {e}")

    canvas = tk.Canvas(root, width=80, height=80, bg="white", highlightthickness=0)
    canvas.pack()
    
    cx, cy = 16, 16
    arrow_pts = [cx, cy, cx, cy + 24, cx + 6, cy + 19, cx + 12, cy + 30, cx + 16, cy + 28, cx + 10, cy + 17, cx + 18, cy + 17]
    canvas.create_polygon(*arrow_pts, fill="", outline="#c084fc", width=5, joinstyle=tk.ROUND)
    canvas.create_polygon(*arrow_pts, fill="", outline="#9333ea", width=3, joinstyle=tk.ROUND)
    canvas.create_polygon(*arrow_pts, fill="#6b21a8", outline="#fefefe", width=1.5, joinstyle=tk.MITER)
    px, py = cx + 22, cy + 14
    pw, ph = 24, 14
    canvas.create_oval(px - 1, py - 1, px + ph + 1, py + ph + 1, fill="", outline="#a855f7", width=3)
    canvas.create_oval(px + pw - ph - 1, py - 1, px + pw + 1, py + ph + 1, fill="", outline="#a855f7", width=3)
    canvas.create_oval(px, py, px + ph, py + ph, fill="#4c1d95", outline="#fefefe", width=1.2)
    canvas.create_oval(px + pw - ph, py, px + pw, py + ph, fill="#4c1d95", outline="#fefefe", width=1.2)
    canvas.create_rectangle(px + ph/2, py, px + pw - ph/2, py + ph, fill="#4c1d95", outline="")
    canvas.create_line(px + ph/2, py, px + pw - ph/2, py, fill="#fefefe", width=1.2)
    canvas.create_line(px + ph/2, py + ph, px + pw - ph/2, py + ph, fill="#fefefe", width=1.2)
    canvas.create_text(px + pw/2, py + ph/2, text="AI", fill="#fefefe", font=("Segoe UI", 7, "bold"))

    log("Graphics drawn. Moving off-screen natively...")
    root.geometry("80x80+-9999+-9999")
    
    def listen_udp(target_hwnd):
        log("UDP Thread starting...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 19882))
            log("Bound to 127.0.0.1:19882 successfully.")
        except Exception as e:
            log(f"CRITICAL: Failed to bind UDP socket! {e}\n{traceback.format_exc()}")
            return
            
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        HWND_TOPMOST = -1
        
        while True:
            try:
                data, _ = sock.recvfrom(64)
                if data == b"HIDE":
                    user32.SetWindowPos(target_hwnd, HWND_TOPMOST, -9999, -9999, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
                    continue
                parts = data.decode("utf-8").split(",")
                if len(parts) == 2:
                    x, y = int(float(parts[0])), int(float(parts[1]))
                    res = user32.SetWindowPos(target_hwnd, HWND_TOPMOST, x - 16, y - 16, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE)
                    if res == 0:
                        log(f"SetWindowPos FAILED for coordinates {x}, {y}. Error: {ctypes.GetLastError()}")
            except Exception as e:
                log(f"UDP Loop Error: {e}")

    t = threading.Thread(target=listen_udp, args=(hwnd,), daemon=True)
    t.start()
    
    log("Entering Tkinter mainloop...")
    root.mainloop()

if __name__ == "__main__":
    create_overlay()
