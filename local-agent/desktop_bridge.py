"""desktop_bridge.py — Session-1 helper daemon for Voila desktop_automation.

Runs in the USER's real interactive desktop session (Session 1).
Listens on a local TCP socket (default 19881).
Accepts newline-delimited JSON command objects, executes them inside this
process (which has real UIA access + real cursor), and returns JSON responses.

Launch via WMI from the agent (sandbox escape):
    python desktop_bridge.py [--port 19881]

Or the Go tool auto-launches it when the port is not responding.
"""
import sys, os, json, socket, threading, argparse

# Ensure cursor_motion and desktop_tools are importable from same dir
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import desktop_core as dt

BRIDGE_PORT = int(os.environ.get("VOILA_DESKTOP_PORT", "19881"))
_lock = threading.Lock()   # one UIA action at a time

def _handle(conn: socket.socket):
    # Initialize COM for this thread (UIA requires STA)
    import ctypes
    ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    try:
        data = b""
        while not data.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
        if not data.strip() or data.strip() == b"\n":
            conn.close()
            return
        req = json.loads(data.decode("utf-8"))

        action   = req.get("action", "")
        ref      = req.get("ref", "")
        selector = req.get("selector", "")
        value    = req.get("value", "")
        window   = req.get("window") or None
        depth    = int(req.get("depth", 8))
        timeout  = int(req.get("timeout_ms", 5000))

        # Build a fake argparse namespace to reuse dispatch()
        class NS:
            pass
        args = NS()
        args.action   = action
        args.ref      = ref
        args.selector = selector
        args.value    = value
        args.window   = window
        args.depth    = depth
        args.timeout  = timeout

        with _lock:
            result = dt.dispatch(args)

        resp = json.dumps(result, ensure_ascii=False) + "\n"
        conn.sendall(resp.encode("utf-8"))
    except Exception as e:
        err = json.dumps({"ok": False, "error": "platform", "message": str(e)}) + "\n"
        try:
            conn.sendall(err.encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

def _serve(port: int):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(8)
    print(f"[desktop_bridge] Listening on 127.0.0.1:{port}", flush=True)
    while True:
        try:
            conn, _ = srv.accept()
            t = threading.Thread(target=_handle, args=(conn,), daemon=True)
            t.start()
        except Exception:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=BRIDGE_PORT)
    args = parser.parse_args()
    _serve(args.port)
