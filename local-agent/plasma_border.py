"""plasma_border.py - Screen Edge Glowing Plasma Border Overlay for Voila AI.

Inspired by Google Gemini (Android Overlay UI) & Apple Intelligence (Siri in iOS 18 / macOS Sequoia).
Creates an amorphous, unshaped, organic, living aurora glow along the screen perimeter.

Features:
- True 32-bit per-pixel alpha blending via Win32 UpdateLayeredWindow.
- Completely seamless, unshaped liquid/nebula plume — NO lines, NO small rectangles.
- Height strictly bounded by the Windows Taskbar (uses SPI_GETWORKAREA).
- 100% Click-through (WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE).
- Unique, bespoke behavior, palette, wave frequency & plume depth for EVERY phrase defined for the AI popup:
  * "Standing by..." (IDLE): Calm, serene, breathing celestial aurora.
  * "Thinking" (THINKING): Radiant solar coronal flares & golden neural ripple waves.
  * "Searching" (SEARCH): Fast scanning cyan radar wave sweep.
  * "Browsing" (BROWSER): Warm billowing flame orange liquid plumes.
  * "Desktop" (DESKTOP): Deep spatial cosmic nebula (billows up to ~65px in vibrant purple).
  * "Bash" (BASH): Matrix emerald digital pulse ripple with micro-flicker.
  * "I/O" (FILE): Electric indigo data stream packet waves.
  * "MCP Connect" (MCP): Neon fuchsia diamond crystal flares.
  * "Background" (BGTASK): Oceanic turquoise tidal swells.
  * "Processing" (RUNNING): Prismatic hyper-drive energy surge.
- Real-time UDP IPC on port 19885 for state & theme synchronization.
"""

import sys
import os
import time
import math
import json
import argparse
import threading
import socket
import ctypes
from ctypes import wintypes
import numpy as np

# ---------------------------------------------------------------------------
# Win32 Constants & Structs
# ---------------------------------------------------------------------------

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
SPI_GETWORKAREA = 0x0030

WPARAM = ctypes.c_uint64
LPARAM = ctypes.c_int64
LRESULT = ctypes.c_int64

user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

class POINT(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

class SIZE(ctypes.Structure):
    _fields_ = [('cx', ctypes.c_long), ('cy', ctypes.c_long)]

class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [('BlendOp', ctypes.c_byte),
                ('BlendFlags', ctypes.c_byte),
                ('SourceConstantAlpha', ctypes.c_byte),
                ('AlphaFormat', ctypes.c_byte)]

class RECT(ctypes.Structure):
    _fields_ = [('left', ctypes.c_long),
                ('top', ctypes.c_long),
                ('right', ctypes.c_long),
                ('bottom', ctypes.c_long)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER),
                ('bmiColors', wintypes.DWORD * 3)]

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.UINT),
                ('style', wintypes.UINT),
                ('lpfnWndProc', ctypes.c_void_p),
                ('cbClsExtra', ctypes.c_int),
                ('cbWndExtra', ctypes.c_int),
                ('hInstance', wintypes.HINSTANCE),
                ('hIcon', wintypes.HICON),
                ('hCursor', wintypes.HCURSOR),
                ('hbrBackground', wintypes.HBRUSH),
                ('lpszMenuName', wintypes.LPCWSTR),
                ('lpszClassName', wintypes.LPCWSTR),
                ('hIconSm', wintypes.HICON)]

# ---------------------------------------------------------------------------
# Distinct Palettes for Themes & Phrases (BGR float32 arrays)
# ---------------------------------------------------------------------------

THEMES = {
    "gemini": np.array([
        [244, 133, 66],    # Google Blue
        [246, 92, 139],    # Cyber Violet
        [68, 68, 239],     # Coral Red
        [5, 188, 251],     # Amber Gold
        [83, 168, 52],     # Emerald Green
        [244, 133, 66],    # Loop
    ], dtype=np.float32),

    "siri": np.array([
        [255, 240, 0],     # Electric Cyan
        [246, 130, 59],    # Neon Blue
        [247, 85, 168],    # Royal Violet
        [153, 72, 236],    # Hot Magenta
        [22, 115, 249],    # Warm Coral
        [36, 191, 251],    # Amber Gold
        [255, 240, 0],
    ], dtype=np.float32),

    "vibgyor": np.array([
        [211, 0, 148],     # Violet
        [130, 0, 75],      # Indigo
        [255, 110, 0],     # Blue
        [120, 255, 0],     # Green
        [0, 255, 255],     # Yellow
        [0, 127, 255],     # Orange
        [50, 0, 255],      # Red
        [211, 0, 148],
    ], dtype=np.float32),

    "cyber_cyan": np.array([
        [255, 245, 0],     # Pure Cyan
        [241, 102, 99],    # Electric Indigo
        [247, 85, 168],    # Neon Purple
        [233, 165, 14],    # Sky Blue
        [255, 245, 0],
    ], dtype=np.float32),

    "solar_gold": np.array([
        [0, 215, 255],     # Gold
        [20, 100, 255],    # Solar Coral
        [80, 50, 255],     # Plasma Crimson
        [40, 180, 255],    # Amber Flame
        [0, 215, 255],
    ], dtype=np.float32)
}

# Bespoke profile for each phrase defined in Voila AI Popup
STATE_PROFILES = {
    "IDLE": {
        "palette": "THEME",      # Uses the user-selected theme
        "speed": 0.20,
        "base_depth": 30.0,
        "wave_amp1": 12.0,
        "wave_amp2": 6.0,
        "pulse_freq": 2.0,
        "pulse_amp": 0.12,
        "shimmer_freq": 3.0,
        "shimmer_amp": 0.02,
        "peak_alpha": 200.0,
    },
    "THINKING": {
        # Solar Corona / Cognitive neural flare: Amber, Gold, Solar Coral & White
        "palette": np.array([
            [5, 188, 251],     # Amber Gold
            [22, 115, 249],    # Solar Coral
            [255, 255, 255],   # White Cognitive Flash
            [0, 215, 255],     # Rich Gold
            [5, 188, 251],
        ], dtype=np.float32),
        "speed": 0.52,
        "base_depth": 38.0,
        "wave_amp1": 18.0,
        "wave_amp2": 10.0,
        "pulse_freq": 5.5,
        "pulse_amp": 0.20,
        "shimmer_freq": 9.0,
        "shimmer_amp": 0.08,
        "peak_alpha": 225.0,
    },
    "SEARCH": {
        # High-tech Scanning Radar: Electric Cyan & Sky Blue
        "palette": np.array([
            [255, 245, 0],     # Electric Cyan
            [248, 189, 56],    # Sky Blue
            [199, 132, 2],     # Deep Cobalt
            [220, 255, 0],     # Aquamarine
            [255, 245, 0],
        ], dtype=np.float32),
        "speed": 0.68,
        "base_depth": 42.0,
        "wave_amp1": 22.0,
        "wave_amp2": 12.0,
        "pulse_freq": 4.5,
        "pulse_amp": 0.22,
        "shimmer_freq": 7.0,
        "shimmer_amp": 0.07,
        "peak_alpha": 230.0,
    },
    "BROWSER": {
        # Web Navigator: Neon Orange Flame & Warm Peach
        "palette": np.array([
            [22, 115, 249],    # Neon Orange Flame
            [12, 65, 234],     # Crimson Coral
            [116, 186, 253],   # Peach Glow
            [30, 140, 255],    # Amber
            [22, 115, 249],
        ], dtype=np.float32),
        "speed": 0.38,
        "base_depth": 38.0,
        "wave_amp1": 16.0,
        "wave_amp2": 8.0,
        "pulse_freq": 3.2,
        "pulse_amp": 0.16,
        "shimmer_freq": 4.0,
        "shimmer_amp": 0.04,
        "peak_alpha": 215.0,
    },
    "DESKTOP": {
        # Spatial Nebula: Royal Cyber Purple & Lavender (Deepest plumes)
        "palette": np.array([
            [237, 58, 124],    # Royal Purple
            [250, 139, 167],   # Electric Violet
            [252, 132, 192],   # Lavender Flare
            [180, 30, 90],     # Deep Nebula
            [237, 58, 124],
        ], dtype=np.float32),
        "speed": 0.44,
        "base_depth": 46.0,
        "wave_amp1": 24.0,
        "wave_amp2": 14.0,
        "pulse_freq": 4.0,
        "pulse_amp": 0.22,
        "shimmer_freq": 6.0,
        "shimmer_amp": 0.05,
        "peak_alpha": 235.0,
    },
    "BASH": {
        # Cyber Matrix / Terminal Emerald with digital pulse
        "palette": np.array([
            [129, 185, 16],    # Matrix Emerald
            [153, 211, 52],    # Cyber Mint
            [105, 150, 5],     # Dark Matrix
            [200, 255, 100],   # Bright Terminal Glint
            [129, 185, 16],
        ], dtype=np.float32),
        "speed": 0.60,
        "base_depth": 32.0,
        "wave_amp1": 15.0,
        "wave_amp2": 8.0,
        "pulse_freq": 6.5,
        "pulse_amp": 0.18,
        "shimmer_freq": 12.0,
        "shimmer_amp": 0.09,
        "peak_alpha": 220.0,
    },
    "FILE": {
        # Data Stream: Electric Indigo & Periwinkle Twin Waves
        "palette": np.array([
            [241, 102, 99],    # Electric Indigo
            [248, 140, 129],   # Periwinkle
            [202, 56, 67],     # Cobalt
            [255, 200, 180],   # Data Flash
            [241, 102, 99],
        ], dtype=np.float32),
        "speed": 0.48,
        "base_depth": 35.0,
        "wave_amp1": 16.0,
        "wave_amp2": 9.0,
        "pulse_freq": 4.2,
        "pulse_amp": 0.16,
        "shimmer_freq": 5.0,
        "shimmer_amp": 0.05,
        "peak_alpha": 220.0,
    },
    "MCP": {
        # Prismatic Crystal / Neon Fuchsia Diamond
        "palette": np.array([
            [239, 70, 217],    # Hot Fuchsia
            [153, 72, 236],    # Neon Pink
            [211, 38, 192],    # Electric Magenta
            [255, 180, 250],   # Diamond Spark
            [239, 70, 217],
        ], dtype=np.float32),
        "speed": 0.62,
        "base_depth": 40.0,
        "wave_amp1": 20.0,
        "wave_amp2": 11.0,
        "pulse_freq": 5.0,
        "pulse_amp": 0.20,
        "shimmer_freq": 8.5,
        "shimmer_amp": 0.08,
        "peak_alpha": 230.0,
    },
    "BGTASK": {
        # Oceanic Swell / Mystic Turquoise
        "palette": np.array([
            [136, 148, 13],    # Deep Teal
            [166, 184, 20],    # Turquoise
            [212, 234, 94],    # Sea Foam
            [100, 120, 10],    # Deep Trench
            [136, 148, 13],
        ], dtype=np.float32),
        "speed": 0.26,
        "base_depth": 35.0,
        "wave_amp1": 14.0,
        "wave_amp2": 7.0,
        "pulse_freq": 2.5,
        "pulse_amp": 0.15,
        "shimmer_freq": 3.0,
        "shimmer_amp": 0.03,
        "peak_alpha": 210.0,
    },
    "RUNNING": {
        # Hyper-Drive Core / Prismatic Spectrum
        "palette": np.array([
            [244, 133, 66],    # Blue
            [246, 92, 139],    # Violet
            [68, 68, 239],     # Coral Red
            [5, 188, 251],     # Amber Gold
            [83, 168, 52],     # Emerald
            [255, 240, 0],     # Cyan
            [244, 133, 66],
        ], dtype=np.float32),
        "speed": 0.72,
        "base_depth": 42.0,
        "wave_amp1": 20.0,
        "wave_amp2": 12.0,
        "pulse_freq": 6.0,
        "pulse_amp": 0.22,
        "shimmer_freq": 10.0,
        "shimmer_amp": 0.10,
        "peak_alpha": 240.0,
    },
    "SECURITY_HAZARD": {
        # Active Threat Alert: Intense Crimson Coronal Pulses with Amber Flame & White Strobe
        "palette": np.array([
            [0, 0, 255],       # Pure Crimson Red (BGR)
            [0, 140, 255],     # Amber Flame
            [20, 20, 220],     # Blood Coral
            [255, 255, 255],   # White Cognitive Warning Flash
            [0, 0, 255],       # Loopback Crimson
        ], dtype=np.float32),
        "speed": 0.85,
        "base_depth": 48.0,
        "wave_amp1": 26.0,
        "wave_amp2": 14.0,
        "pulse_freq": 7.5,
        "pulse_amp": 0.28,
        "shimmer_freq": 14.0,
        "shimmer_amp": 0.12,
        "peak_alpha": 250.0,
    },
    "ISOLATED": {
        # Host Network Isolation Active: Deep Calm Steel Blue & Ice Cyan Boundary
        "palette": np.array([
            [200, 100, 30],    # Deep Cobalt Blue
            [240, 200, 80],    # Steel Cyan
            [255, 240, 150],   # Ice White
            [180, 80, 20],     # Midnight Blue
            [200, 100, 30],    # Loopback Cobalt
        ], dtype=np.float32),
        "speed": 0.20,
        "base_depth": 32.0,
        "wave_amp1": 10.0,
        "wave_amp2": 5.0,
        "pulse_freq": 1.8,
        "pulse_amp": 0.10,
        "shimmer_freq": 3.0,
        "shimmer_amp": 0.03,
        "peak_alpha": 200.0,
    }
}

def sample_palette_vectorized(palette, phases):
    """Vectorized linear interpolation across palette colors for an array of phases [0, 1)."""
    p = (phases % 1.0) * (len(palette) - 1)
    idx = np.floor(p).astype(np.int32)
    idx = np.clip(idx, 0, len(palette) - 2)
    frac = (p - idx)[:, None]
    c1 = palette[idx]
    c2 = palette[idx + 1]
    return c1 + (c2 - c1) * frac

# ---------------------------------------------------------------------------
# Amorphous Plasma Window (True 32-bit Alpha Blending)
# ---------------------------------------------------------------------------

class AmorphousPlasmaOverlay:
    def __init__(self, theme="gemini", port=19885):
        self.theme_name = theme if theme in THEMES else "gemini"
        self.port = port
        self.state = "IDLE"  # "IDLE", "THINKING", "SEARCH", "BASH", "DESKTOP", etc.
        self.enabled = True
        self.running = True
        self.alpha_entrance = 0.0
        self.start_time = time.time()
        self.settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plasma_settings.json")
        self.load_settings()

        # Set DPI Awareness
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

        # Query work area excluding the taskbar
        self.update_work_area()

        # Register window class
        self.hInstance = kernel32.GetModuleHandleW(None)
        self.wnd_proc_cb = WNDPROC(self.wnd_proc)

        wcls = WNDCLASSEXW()
        wcls.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wcls.style = 0
        wcls.lpfnWndProc = ctypes.cast(self.wnd_proc_cb, ctypes.c_void_p)
        wcls.cbClsExtra = 0
        wcls.cbWndExtra = 0
        wcls.hInstance = self.hInstance
        wcls.hIcon = 0
        wcls.hCursor = 0
        wcls.hbrBackground = 0
        wcls.lpszMenuName = None
        wcls.lpszClassName = "VoilaAmorphousAuroraClass"
        wcls.hIconSm = 0
        user32.RegisterClassExW(ctypes.byref(wcls))

        # Create layered, transparent, click-through window
        ex_style = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | 
                    WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            "VoilaAmorphousAuroraClass",
            "VoilaAmorphousAurora",
            WS_POPUP | WS_VISIBLE,
            self.wx, self.wy, self.ww, self.wh,
            0, 0, self.hInstance, 0
        )

        # Allocate memory DC & DIB Section
        self.init_dib_buffer()

        # Maximum depth of the blooming light plumes
        self.MAX_D = 65
        self.top_y = np.arange(self.MAX_D, dtype=np.float32).reshape(-1, 1)
        self.bot_y = np.arange(self.MAX_D, dtype=np.float32).reshape(-1, 1)
        self.side_x = np.arange(self.MAX_D, dtype=np.float32).reshape(1, -1)

        self.x_indices = np.arange(self.ww, dtype=np.float32)
        self.y_indices = np.arange(self.wh, dtype=np.float32)

        # Start IPC listener thread
        self.start_ipc_server()

    def wnd_proc(self, hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def update_work_area(self):
        rect = RECT()
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        self.wx = rect.left
        self.wy = rect.top
        self.ww = max(100, rect.right - rect.left)
        self.wh = max(100, rect.bottom - rect.top)

    def init_dib_buffer(self):
        self.hdc_screen = user32.GetDC(0)
        self.hdc_mem = gdi32.CreateCompatibleDC(self.hdc_screen)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self.ww
        bmi.bmiHeader.biHeight = -self.wh  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0

        self.p_bits = ctypes.c_void_p()
        self.hbmp = gdi32.CreateDIBSection(
            self.hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(self.p_bits), 0, 0
        )
        gdi32.SelectObject(self.hdc_mem, self.hbmp)

        buffer = (ctypes.c_uint8 * (self.wh * self.ww * 4)).from_address(self.p_bits.value)
        self.arr = np.frombuffer(buffer, dtype=np.uint8).reshape((self.wh, self.ww, 4))

        self.blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        self.pt_src = POINT(0, 0)
        self.pt_dst = POINT(self.wx, self.wy)
        self.sz = SIZE(self.ww, self.wh)

    def load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "theme" in data and data["theme"] in THEMES:
                        self.theme_name = data["theme"]
                    if "state" in data:
                        self.state = data["state"]
                        if self.state == "OFF":
                            self.enabled = False
        except Exception:
            pass

    def save_settings(self):
        try:
            persisted_state = "OFF" if not self.enabled else ("IDLE" if self.state in ("OFF", "BLANK", "PAUSE") else self.state)
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump({"theme": self.theme_name, "state": persisted_state}, f, indent=2)
        except Exception:
            pass

    def clear_screen(self):
        try:
            self.arr.fill(0)
            user32.UpdateLayeredWindow(
                self.hwnd, self.hdc_screen,
                ctypes.byref(self.pt_dst), ctypes.byref(self.sz),
                self.hdc_mem, ctypes.byref(self.pt_src),
                0, ctypes.byref(self.blend), ULW_ALPHA
            )
        except Exception:
            pass

    def start_ipc_server(self):
        def _listen():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", self.port))
            except Exception:
                return
            sock.settimeout(1.0)
            while self.running:
                try:
                    data, _ = sock.recvfrom(1024)
                    if not data:
                        continue
                    msg = data.decode("utf-8").strip()
                    self.handle_ipc_message(msg)
                except socket.timeout:
                    continue
                except Exception:
                    break
            try:
                sock.close()
            except Exception:
                pass

        t = threading.Thread(target=_listen, daemon=True)
        t.start()

    def handle_ipc_message(self, msg):
        try:
            if msg.startswith("THEME:"):
                theme = msg.split(":", 1)[1].strip().lower()
                if theme in THEMES:
                    self.theme_name = theme
                    self.save_settings()
            elif msg.startswith("STATE:"):
                state = msg.split(":", 1)[1].strip().upper()
                if state in ("OFF", "BLANK", "PAUSE"):
                    # Transient blanking (e.g. during screen captures or brief pause)
                    # We clear the screen but DO NOT permanently disable or corrupt saved settings on disk!
                    self.state = "OFF"
                    self.clear_screen()
                elif state in ("ON", "ACTIVE", "ENABLE"):
                    self.enabled = True
                    self.state = "IDLE"
                    self.save_settings()
                else:
                    # Active AI states: IDLE, THINKING, SEARCH, BROWSER, DESKTOP, BASH, FILE, MCP, BGTASK, RUNNING
                    if not self.enabled:
                        # If explicitly disabled via settings, stay disabled
                        return
                    self.state = state
                    # NOTE: Do NOT call self.save_settings() on high-frequency transient state changes!
            elif msg in ("DISABLE", "OFF", "STOP"):
                self.enabled = False
                self.state = "OFF"
                self.save_settings()
                self.clear_screen()
            elif msg in ("ENABLE", "ON", "START", "ACTIVE"):
                self.enabled = True
                self.state = "IDLE"
                self.save_settings()
            elif msg in ("EXIT", "QUIT"):
                self.running = False
                self.clear_screen()
        except Exception:
            pass

    def run(self):
        msg = wintypes.MSG()

        while self.running:
            # Non-blocking message pump
            while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                if msg.message == 0x0012:  # WM_QUIT
                    self.running = False
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            if not self.running:
                break

            t0 = time.time()
            elapsed = t0 - self.start_time

            # Entrance fade-in
            if self.alpha_entrance < 1.0:
                self.alpha_entrance = min(1.0, self.alpha_entrance + 0.04)

            if not self.enabled or self.state == "OFF":
                self.clear_screen()
                time.sleep(0.1)
                continue

            # Fetch active state profile
            prof = STATE_PROFILES.get(self.state, STATE_PROFILES["IDLE"])

            # Resolve palette
            if isinstance(prof["palette"], str) and prof["palette"] == "THEME":
                palette = THEMES.get(self.theme_name, THEMES["gemini"])
            else:
                palette = prof["palette"]

            speed = prof["speed"]
            base_depth = prof["base_depth"]
            wave_amp1 = prof["wave_amp1"]
            wave_amp2 = prof["wave_amp2"]
            pulse = (1.0 - prof["pulse_amp"] + prof["pulse_amp"] * math.sin(elapsed * prof["pulse_freq"])) * self.alpha_entrance
            shimmer = 1.0 + prof["shimmer_amp"] * math.sin(elapsed * prof["shimmer_freq"])
            peak_alpha = prof["peak_alpha"]

            # Clear buffer to pure transparent (0, 0, 0, 0)
            self.arr.fill(0)

            D = self.MAX_D

            # ─────────────────────────────────────────────────────────────
            # 1. TOP BORDER (Billowing amorphous plume)
            # ─────────────────────────────────────────────────────────────
            top_wave = base_depth + (wave_amp1 * np.sin(self.x_indices * 0.012 + elapsed * (speed * 10.0)) +
                                    wave_amp2 * np.cos(self.x_indices * 0.024 - elapsed * (speed * 7.0)))
            top_u = np.clip(self.top_y / top_wave, 0.0, 1.0)
            top_cos = np.maximum(0.0, np.cos(top_u * (math.pi / 2)))
            top_alpha = (top_cos * top_cos * (peak_alpha * pulse * shimmer)).astype(np.float32)
            top_alpha[:3, :] = np.clip(top_alpha[:3, :] * 1.35, 0, 255)

            top_phases = (self.x_indices / self.ww + elapsed * speed) % 1.0
            top_colors = sample_palette_vectorized(palette, top_phases)

            top_b = np.clip(top_alpha * (top_colors[:, 0] / 255.0), 0, 255).astype(np.uint8)
            top_g = np.clip(top_alpha * (top_colors[:, 1] / 255.0), 0, 255).astype(np.uint8)
            top_r = np.clip(top_alpha * (top_colors[:, 2] / 255.0), 0, 255).astype(np.uint8)
            top_a = np.clip(top_alpha, 0, 255).astype(np.uint8)

            self.arr[:D, :, 0] = top_b
            self.arr[:D, :, 1] = top_g
            self.arr[:D, :, 2] = top_r
            self.arr[:D, :, 3] = top_a

            # ─────────────────────────────────────────────────────────────
            # 2. BOTTOM BORDER (Stops cleanly at top of Taskbar!)
            # ─────────────────────────────────────────────────────────────
            bot_wave = base_depth + (wave_amp1 * np.sin(self.x_indices * 0.014 - elapsed * (speed * 9.0)) +
                                    wave_amp2 * np.cos(self.x_indices * 0.028 + elapsed * (speed * 6.5)))
            bot_u = np.clip((D - 1 - self.bot_y) / bot_wave, 0.0, 1.0)
            bot_cos = np.maximum(0.0, np.cos(bot_u * (math.pi / 2)))
            bot_alpha = (bot_cos * bot_cos * (peak_alpha * pulse * shimmer)).astype(np.float32)
            bot_alpha[-3:, :] = np.clip(bot_alpha[-3:, :] * 1.35, 0, 255)

            bot_phases = (0.50 + self.x_indices / self.ww - elapsed * speed) % 1.0
            bot_colors = sample_palette_vectorized(palette, bot_phases)

            bot_b = np.clip(bot_alpha * (bot_colors[:, 0] / 255.0), 0, 255).astype(np.uint8)
            bot_g = np.clip(bot_alpha * (bot_colors[:, 1] / 255.0), 0, 255).astype(np.uint8)
            bot_r = np.clip(bot_alpha * (bot_colors[:, 2] / 255.0), 0, 255).astype(np.uint8)
            bot_a = np.clip(bot_alpha, 0, 255).astype(np.uint8)

            self.arr[self.wh - D:, :, 0] = np.maximum(self.arr[self.wh - D:, :, 0], bot_b)
            self.arr[self.wh - D:, :, 1] = np.maximum(self.arr[self.wh - D:, :, 1], bot_g)
            self.arr[self.wh - D:, :, 2] = np.maximum(self.arr[self.wh - D:, :, 2], bot_r)
            self.arr[self.wh - D:, :, 3] = np.maximum(self.arr[self.wh - D:, :, 3], bot_a)

            # ─────────────────────────────────────────────────────────────
            # 3. LEFT BORDER
            # ─────────────────────────────────────────────────────────────
            left_wave = base_depth + (wave_amp1 * np.sin(self.y_indices * 0.015 + elapsed * (speed * 8.0)) +
                                     wave_amp2 * np.cos(self.y_indices * 0.030 - elapsed * (speed * 6.0)))
            left_u = np.clip(self.side_x / left_wave[:, None], 0.0, 1.0)
            left_cos = np.maximum(0.0, np.cos(left_u * (math.pi / 2)))
            left_alpha = (left_cos * left_cos * (peak_alpha * pulse * shimmer)).astype(np.float32)
            left_alpha[:, :3] = np.clip(left_alpha[:, :3] * 1.35, 0, 255)

            left_phases = (0.75 + self.y_indices / self.wh + elapsed * speed) % 1.0
            left_colors = sample_palette_vectorized(palette, left_phases)

            left_b = np.clip(left_alpha * (left_colors[:, 0, None] / 255.0), 0, 255).astype(np.uint8)
            left_g = np.clip(left_alpha * (left_colors[:, 1, None] / 255.0), 0, 255).astype(np.uint8)
            left_r = np.clip(left_alpha * (left_colors[:, 2, None] / 255.0), 0, 255).astype(np.uint8)
            left_a = np.clip(left_alpha, 0, 255).astype(np.uint8)

            self.arr[:, :D, 0] = np.maximum(self.arr[:, :D, 0], left_b)
            self.arr[:, :D, 1] = np.maximum(self.arr[:, :D, 1], left_g)
            self.arr[:, :D, 2] = np.maximum(self.arr[:, :D, 2], left_r)
            self.arr[:, :D, 3] = np.maximum(self.arr[:, :D, 3], left_a)

            # ─────────────────────────────────────────────────────────────
            # 4. RIGHT BORDER
            # ─────────────────────────────────────────────────────────────
            right_wave = base_depth + (wave_amp1 * np.sin(self.y_indices * 0.016 - elapsed * (speed * 9.5)) +
                                      wave_amp2 * np.cos(self.y_indices * 0.032 + elapsed * (speed * 7.5)))
            right_u = np.clip((D - 1 - self.side_x) / right_wave[:, None], 0.0, 1.0)
            right_cos = np.maximum(0.0, np.cos(right_u * (math.pi / 2)))
            right_alpha = (right_cos * right_cos * (peak_alpha * pulse * shimmer)).astype(np.float32)
            right_alpha[:, -3:] = np.clip(right_alpha[:, -3:] * 1.35, 0, 255)

            right_phases = (0.25 + self.y_indices / self.wh - elapsed * speed) % 1.0
            right_colors = sample_palette_vectorized(palette, right_phases)

            right_b = np.clip(right_alpha * (right_colors[:, 0, None] / 255.0), 0, 255).astype(np.uint8)
            right_g = np.clip(right_alpha * (right_colors[:, 1, None] / 255.0), 0, 255).astype(np.uint8)
            right_r = np.clip(right_alpha * (right_colors[:, 2, None] / 255.0), 0, 255).astype(np.uint8)
            right_a = np.clip(right_alpha, 0, 255).astype(np.uint8)

            self.arr[:, self.ww - D:, 0] = np.maximum(self.arr[:, self.ww - D:, 0], right_b)
            self.arr[:, self.ww - D:, 1] = np.maximum(self.arr[:, self.ww - D:, 1], right_g)
            self.arr[:, self.ww - D:, 2] = np.maximum(self.arr[:, self.ww - D:, 2], right_r)
            self.arr[:, self.ww - D:, 3] = np.maximum(self.arr[:, self.ww - D:, 3], right_a)

            # ─────────────────────────────────────────────────────────────
            # Blit directly to desktop with 32-bit Alpha Blending
            # ─────────────────────────────────────────────────────────────
            user32.UpdateLayeredWindow(
                self.hwnd, self.hdc_screen,
                ctypes.byref(self.pt_dst), ctypes.byref(self.sz),
                self.hdc_mem, ctypes.byref(self.pt_src),
                0, ctypes.byref(self.blend), ULW_ALPHA
            )

            # Smooth 60 FPS pacing
            dt = time.time() - t0
            sleep_time = max(0.001, 0.016 - dt)
            time.sleep(sleep_time)

        # Cleanup Win32 resources
        self.cleanup()

    def cleanup(self):
        try:
            gdi32.DeleteObject(self.hbmp)
            gdi32.DeleteDC(self.hdc_mem)
            user32.ReleaseDC(0, self.hdc_screen)
            user32.DestroyWindow(self.hwnd)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Voila Amorphous Screen Edge Plasma Glow Overlay")
    parser.add_argument("--theme", type=str, default="gemini", choices=list(THEMES.keys()), help="Initial theme")
    parser.add_argument("--port", type=int, default=19885, help="UDP IPC control port")
    parser.add_argument("--state", type=str, default=None, help="Initial state override (e.g. IDLE, OFF)")
    args, _ = parser.parse_known_args()

    overlay = AmorphousPlasmaOverlay(theme=args.theme, port=args.port)
    if args.state:
        overlay.state = args.state.upper()
        if overlay.state == "OFF":
            overlay.enabled = False
        else:
            overlay.enabled = True
    overlay.run()

if __name__ == "__main__":
    main()
