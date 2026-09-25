import uiautomation as auto
import ctypes, subprocess, sys

print("Enumerating root children...")
r = auto.GetRootControl()
w = r.GetFirstChildControl()
n = 0
while w and n < 80:
    try:
        name = w.Name
        cls  = w.ClassName
        pid  = w.ProcessId
        print(f"  [{n}] name={name!r:40s} cls={cls!r:40s} pid={pid}")
    except Exception as e:
        print(f"  [{n}] ERROR: {e}")
    try:
        w = w.GetNextSiblingControl()
    except:
        break
    n += 1

print("\n--- Looking for Start-related windows ---")
try:
    sm = auto.WindowControl(searchDepth=2, ClassName="Windows.UI.Core.CoreWindow")
    print("CoreWindow found:", sm.Name, sm.ProcessId)
except Exception as e:
    print("CoreWindow:", e)

try:
    sm2 = auto.PaneControl(searchDepth=3, Name="Start")
    print("Start Pane found:", sm2.ClassName, sm2.ProcessId)
except Exception as e:
    print("Start Pane:", e)

# Try win32 approach
user32 = ctypes.windll.user32
hwnd = user32.FindWindowW("Shell_TrayWnd", None)
print(f"Shell_TrayWnd hwnd={hwnd}")

hwnd2 = user32.FindWindowW("DV2ControlHost", None)
print(f"DV2ControlHost (Win10 start) hwnd={hwnd2}")

hwnd3 = user32.FindWindowW("Windows.UI.Core.CoreWindow", "Start")
print(f"CoreWindow Start hwnd={hwnd3}")
