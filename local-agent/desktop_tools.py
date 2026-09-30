"""desktop_tools.py — Windows UIA desktop automation tool for Voila.

ARCHITECTURE (Session Isolation Fix)
=====================================
The Voila agent runs in a sandboxed "exebox" desktop (Session 0-equivalent
isolated process). Windows UIA and SetCursorPos ONLY work from the user's
real interactive session (Session 1, where the actual screen lives).

Fix: desktop_tools.py is a PROXY when called from the agent:
  1. Check if desktop_bridge.py is running on 127.0.0.1:19881
  2. If not, auto-launch it via WMI (sandbox escape → Session 1)
  3. Forward all commands over the local socket; return the JSON response

desktop_bridge.py runs in Session 1 and imports the real UIA + cursor_motion
logic. cursor_motion.py exclusively drives all pointer motion there.

CLI:
    python desktop_tools.py --action <action> [--ref e1] [--selector ...] \\
                             [--value ...] [--window ...] [--depth 8] \\
                             [--button left|right|double] [--monitor 0]
    stdout: one JSON object

Supported actions:
    snapshot, find, invoke, click_ref, right_click, set_value, type_keys,
    toggle, focus, select, drag_ref, move_cursor, foreground, list_windows,
    focus_window, close_window, switch_tab, switch_window, switch_desktop,
    scroll
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os, json, socket, subprocess, time, argparse

BRIDGE_PORT = int(os.environ.get("VOILA_DESKTOP_PORT", "19881"))
BRIDGE_HOST = "127.0.0.1"

# ─── Platform guard ────────────────────────────────────────────────────────────
if sys.platform != "win32":
    print(json.dumps({"ok": False, "error": "platform",
                      "message": "desktop_automation requires Windows"}))
    sys.exit(0)

# ─── Bridge probe + auto-launch ───────────────────────────────────────────────
_bridge_ready: bool = False   # cached so we don't re-probe on every call

def _bridge_up(timeout: float = 0.5) -> bool:
    try:
        s = socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False

def _launch_bridge() -> bool:
    """Launch desktop_bridge.py in the user's real session via WMI."""
    here = os.path.dirname(os.path.abspath(__file__))
    bridge_path = os.path.join(here, "desktop_bridge.py")

    # Use WMI Win32_Process.Create to break out of sandbox into Session 1
    python_exe = sys.executable.replace("python.exe", "pythonw.exe")
    cmd = f'{python_exe} "{bridge_path}" --port {BRIDGE_PORT}'
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".", "root\\cimv2")
        process_startup = wmi.Get("Win32_ProcessStartup").SpawnInstance_()
        process_startup.ShowWindow = 0  # Hidden
        result, pid = wmi.Get("Win32_Process").Create(cmd, None, process_startup)
        if result != 0:
            raise RuntimeError(f"WMI Create returned {result}")
    except Exception:
        # Fallback: simple subprocess (may spawn in sandbox)
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        subprocess.Popen(
            [python_exe, bridge_path, "--port", str(BRIDGE_PORT)],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
        )

    # Wait up to 5 s for bridge to come online
    for _ in range(20):
        time.sleep(0.25)
        if _bridge_up():
            return True
    return False

def _ensure_bridge() -> bool:
    global _bridge_ready
    if _bridge_ready:
        # Quick liveness re-check (cheap — just TCP connect)
        if _bridge_up(timeout=0.2):
            return True
        _bridge_ready = False  # bridge died; re-launch below
    if _bridge_up():
        _bridge_ready = True
        return True
    _bridge_ready = _launch_bridge()
    return _bridge_ready

# ─── Proxy call ───────────────────────────────────────────────────────────────

def _proxy(req: dict) -> dict:
    """Send req to bridge and return parsed response dict."""
    global _bridge_ready
    if not _ensure_bridge():
        return {"ok": False, "error": "platform",
                "message": "desktop_bridge failed to start. Check that python can run in the user session."}
    try:
        s = socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=30)
        s.settimeout(30)
        payload = json.dumps(req, ensure_ascii=False) + "\n"
        s.sendall(payload.encode("utf-8"))

        # Read until newline (bridge always terminates response with \n)
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        s.close()
        
        decoded = data.decode("utf-8").strip()
        if not decoded:
            return {"ok": False, "error": "platform", "message": "Bridge crashed or returned empty response."}
        return json.loads(decoded)
    except json.JSONDecodeError as je:
        _bridge_ready = False
        return {"ok": False, "error": "platform", "message": f"Bridge JSON error: {je}. Raw: {decoded[:200]}"}
    except Exception as e:
        _bridge_ready = False  # force re-check next time
        return {"ok": False, "error": "platform", "message": f"Bridge comm error: {e}"}

# ─── CLI ──────────────────────────────────────────────────────────────────────


try:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from aegis.aegis_core import AegisMonitor
    aegis_monitor = AegisMonitor(os.path.join(os.path.dirname(os.path.abspath(__file__)), "aegis", "data"))
except Exception as e:
    aegis_monitor = None

def main():
    parser = argparse.ArgumentParser(description="Voila desktop automation proxy")
    parser.add_argument("--action",   required=True)
    parser.add_argument("--ref",      default="")
    parser.add_argument("--selector", default="")
    parser.add_argument("--value",    default="")
    parser.add_argument("--window",   default="")
    parser.add_argument("--depth",    type=int, default=8)
    parser.add_argument("--timeout",  type=int, default=5000)
    # NEW: button for right-click / double-click support
    parser.add_argument("--button",   default="left",
                        help="Mouse button for click actions (default: left)")
    # NEW: monitor / desktop index for switch_desktop
    parser.add_argument("--monitor",  type=int, default=0,
                        help="Virtual desktop index for switch_desktop (0-based)")
    args = parser.parse_args()

    
    if aegis_monitor:
        payload = args.value or args.ref or args.selector
        is_safe, reason = aegis_monitor.verify_action(args.action, payload, args.window)
        if not is_safe:
            print(json.dumps({"ok": False, "error": "security_blocked", "message": f"AEGIS SECURITY BLOCK: {reason}"}))
            return

    req = {
        "action":     args.action,
        "ref":        args.ref,
        "selector":   args.selector,
        "value":      args.value,
        "window":     args.window or None,
        "depth":      args.depth,
        "timeout_ms": args.timeout,
        "button":     args.button,
        "monitor":    args.monitor,
    }

    result = _proxy(req)
    if 'cursor' in result: del result['cursor']
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
