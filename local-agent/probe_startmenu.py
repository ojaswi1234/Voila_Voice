"""Probe script to be run via desktop_bridge (session 1) to discover Start Menu window structure."""
import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import uiautomation as auto
import ctypes, json

result = {}

# --- Enumerate root children ---
windows = []
try:
    r = auto.GetRootControl()
    w = r.GetFirstChildControl()
    n = 0
    while w and n < 80:
        try:
            entry = {
                "name":  w.Name,
                "class": w.ClassName,
                "pid":   w.ProcessId,
                "hwnd":  w.NativeWindowHandle,
            }
            windows.append(entry)
        except Exception as e:
            windows.append({"error": str(e)})
        try:
            w = w.GetNextSiblingControl()
        except:
            break
        n += 1
except Exception as e:
    windows = [{"root_error": str(e)}]
result["root_children"] = windows

# --- Win32 HWND probes ---
user32 = ctypes.windll.user32
probes = {
    "Shell_TrayWnd":          user32.FindWindowW("Shell_TrayWnd", None),
    "DV2ControlHost":         user32.FindWindowW("DV2ControlHost", None),
    "CoreWindow_Start":       user32.FindWindowW("Windows.UI.Core.CoreWindow", "Start"),
    "Windows.UI.Core.CoreWindow": user32.FindWindowW("Windows.UI.Core.CoreWindow", None),
}
result["hwnd_probes"] = probes

# --- Foreground window ---
try:
    fg = auto.GetForegroundControl()
    result["foreground"] = {"name": fg.Name, "class": fg.ClassName, "pid": fg.ProcessId}
except Exception as e:
    result["foreground"] = {"error": str(e)}

print(json.dumps(result, indent=2, default=str))
