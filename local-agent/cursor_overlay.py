"""cursor_overlay.py — AI cursor overlay window for Voila.

Single-agent mode (default): behaves exactly as before.
Graphify multi-agent mode: launched with --port, --name, --color-* args
so each agent gets its own independently colored, named cursor.

Args (all optional — defaults match original single-agent behavior):
  --port          UDP port to listen on         (default: 19882)
  --name          Label shown on cursor         (default: AI)
  --color-fill    Arrow fill color              (default: #6b21a8)
  --color-outline Arrow outer glow color        (default: #c084fc)
  --color-glow    Arrow inner glow color        (default: #9333ea)
  --color-badge   Badge background color        (default: #4c1d95)
  --color-text    Badge text color              (default: #fefefe)
"""
import sys
import argparse
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


def create_overlay():
    cfg = parse_args()

    log(f"Starting overlay: port={cfg.port} name={cfg.name} fill={cfg.color_fill}")
    root = tk.Tk()
    root.title(f"Voila AI Cursor [{cfg.name}]")
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

    # --- Draw arrow cursor (scaled-down, ~40% smaller than original) ---
    cx, cy = 16, 16
    arrow_pts = [
        cx, cy,
        cx, cy + 15,
        cx + 4, cy + 12,
        cx + 8, cy + 19,
        cx + 10, cy + 18,
        cx + 6, cy + 11,
        cx + 11, cy + 11,
    ]
    # Outer glow
    canvas.create_polygon(*arrow_pts, fill="", outline=cfg.color_outline, width=3, joinstyle=tk.ROUND)
    # Mid glow
    canvas.create_polygon(*arrow_pts, fill="", outline=cfg.color_glow, width=2, joinstyle=tk.ROUND)
    # Filled arrow
    canvas.create_polygon(*arrow_pts, fill=cfg.color_fill, outline=cfg.color_text, width=1.0, joinstyle=tk.MITER)

    # --- Draw agent name badge ---
    px, py = cx + 14, cy + 9
    pw, ph = 18, 10
    # Badge left cap
    canvas.create_oval(px - 1, py - 1, px + ph + 1, py + ph + 1,
                       fill="", outline=cfg.color_glow, width=2)
    # Badge right cap
    canvas.create_oval(px + pw - ph - 1, py - 1, px + pw + 1, py + ph + 1,
                       fill="", outline=cfg.color_glow, width=2)
    # Badge left fill
    canvas.create_oval(px, py, px + ph, py + ph,
                       fill=cfg.color_badge, outline=cfg.color_text, width=1.0)
    # Badge right fill
    canvas.create_oval(px + pw - ph, py, px + pw, py + ph,
                       fill=cfg.color_badge, outline=cfg.color_text, width=1.0)
    # Badge center fill
    canvas.create_rectangle(px + ph/2, py, px + pw - ph/2, py + ph,
                             fill=cfg.color_badge, outline="")
    # Badge border lines
    canvas.create_line(px + ph/2, py, px + pw - ph/2, py,
                       fill=cfg.color_text, width=1.0)
    canvas.create_line(px + ph/2, py + ph, px + pw - ph/2, py + ph,
                       fill=cfg.color_text, width=1.0)

    # Agent name label — truncate to 4 chars max to fit the badge
    label = cfg.name[:4] if len(cfg.name) > 4 else cfg.name
    canvas.create_text(px + pw/2, py + ph/2, text=label,
                       fill=cfg.color_text, font=("Segoe UI", 5, "bold"))

    log(f"Graphics drawn for agent '{cfg.name}'. Moving off-screen natively...")
    root.geometry("80x80+-9999+-9999")

    def listen_udp(target_hwnd):
        log(f"UDP Thread starting on port {cfg.port}...")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", cfg.port))
            log(f"Bound to 127.0.0.1:{cfg.port} successfully.")
        except Exception as e:
            log(f"CRITICAL: Failed to bind UDP socket on port {cfg.port}! {e}\n{traceback.format_exc()}")
            return

        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]

        SWP_NOSIZE    = 0x0001
        SWP_NOACTIVATE = 0x0010
        HWND_TOPMOST  = -1

        while True:
            try:
                data, _ = sock.recvfrom(64)
                if data == b"HIDE":
                    user32.SetWindowPos(target_hwnd, HWND_TOPMOST,
                                        -9999, -9999, 0, 0,
                                        SWP_NOSIZE | SWP_NOACTIVATE)
                    continue
                parts = data.decode("utf-8").split(",")
                if len(parts) == 2:
                    x, y = int(float(parts[0])), int(float(parts[1]))
                    res = user32.SetWindowPos(target_hwnd, HWND_TOPMOST,
                                              x - 16, y - 16, 0, 0,
                                              SWP_NOSIZE | SWP_NOACTIVATE)
                    if res == 0:
                        log(f"SetWindowPos FAILED for coordinates {x}, {y}. Error: {ctypes.GetLastError()}")
            except Exception as e:
                log(f"UDP Loop Error: {e}")

    t = threading.Thread(target=listen_udp, args=(hwnd,), daemon=True)
    t.start()

    log(f"Entering Tkinter mainloop for agent '{cfg.name}'...")
    root.mainloop()


if __name__ == "__main__":
    create_overlay()
