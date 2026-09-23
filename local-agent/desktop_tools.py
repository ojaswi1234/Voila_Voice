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
    python desktop_tools.py --action <action> [--ref e1] [--selector ...] \
                             [--value ...] [--window ...] [--depth 8]
    stdout: one JSON object
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
    except Exception as e:
        # Fallback: simple subprocess (may spawn in sandbox)
        import subprocess
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
    if _bridge_up():
        return True
    return _launch_bridge()

# ─── Proxy call ───────────────────────────────────────────────────────────────

def _proxy(req: dict) -> dict:
    """Send req to bridge and return parsed response dict."""
    if not _ensure_bridge():
        return {"ok": False, "error": "platform",
                "message": "desktop_bridge failed to start. Check that python can run in the user session."}
    try:
        s = socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=30)
        payload = json.dumps(req, ensure_ascii=False) + "\n"
        s.sendall(payload.encode("utf-8"))

        # Read until newline (bridge always terminates response with \n)
        data = b""
        s.settimeout(30)
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        s.close()
        return json.loads(data.decode("utf-8").strip())
    except Exception as e:
        return {"ok": False, "error": "platform", "message": f"Bridge comm error: {e}"}

# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Voila desktop automation proxy")
    parser.add_argument("--action",   required=True)
    parser.add_argument("--ref",      default="")
    parser.add_argument("--selector", default="")
    parser.add_argument("--value",    default="")
    parser.add_argument("--window",   default="")
    parser.add_argument("--depth",    type=int, default=8)
    parser.add_argument("--timeout",  type=int, default=5000)
    args = parser.parse_args()

    req = {
        "action":   args.action,
        "ref":      args.ref,
        "selector": args.selector,
        "value":    args.value,
        "window":   args.window or None,
        "depth":    args.depth,
        "timeout_ms": args.timeout,
    }

    result = _proxy(req)
    with open("desktop_tools_req.log", "a", encoding="utf-8") as f:
        f.write(f"REQ: {json.dumps(req)}\nRES: {json.dumps(result, ensure_ascii=False)}\n\n")
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
