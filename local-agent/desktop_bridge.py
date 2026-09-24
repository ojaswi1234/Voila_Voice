"""desktop_bridge.py — Session-1 helper daemon for Voila desktop_automation.

Runs in the USER's real interactive desktop session (Session 1).
Listens on a local TCP socket (default 19881).
Accepts newline-delimited JSON command objects, executes them inside this
process (which has real UIA access + real cursor), and returns JSON responses.

Launch via WMI from the agent (sandbox escape):
    python desktop_bridge.py [--port 19881]

Or the Go tool auto-launches it when the port is not responding.
"""
import sys, os, json, socket, threading, argparse, ctypes

# Ensure cursor_motion and desktop_core are importable from same dir
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Initialize COM for the MAIN thread once (STA) ──
# Worker threads call CoInitializeEx individually but we do the main thread here.
ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED

# ── Force DPI Awareness ──
# Ensures UIA coordinates match physical screen coordinates on scaled displays (>100% DPI).
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import desktop_core as dt

BRIDGE_PORT = int(os.environ.get("VOILA_DESKTOP_PORT", "19881"))
_lock = threading.Lock()   # one UIA action at a time (per-process)

# ── Cross-process Global UIA Mutex (Graphify multi-agent anti-choking) ────────
# When multiple bridge instances run simultaneously (one per Graphify agent),
# they must take turns calling the Windows UIA COM layer to avoid COM deadlocks.
# This Named Mutex is shared across ALL bridge processes on the same machine.
# In single-agent mode (VOILA_AGENT_INDEX not set), this code path is skipped.
_IS_GRAPHIFY_AGENT = os.environ.get("VOILA_AGENT_INDEX") is not None

_global_uia_mutex = None
if _IS_GRAPHIFY_AGENT:
    try:
        _global_uia_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "VoilaGlobalUIAMutex")
    except Exception:
        _global_uia_mutex = None  # graceful degradation

def _acquire_global_uia():
    """Acquire the cross-process UIA mutex. No-op in single-agent mode."""
    if _global_uia_mutex:
        ctypes.windll.kernel32.WaitForSingleObject(_global_uia_mutex, 15000)  # 15s timeout

def _release_global_uia():
    """Release the cross-process UIA mutex. No-op in single-agent mode."""
    if _global_uia_mutex:
        ctypes.windll.kernel32.ReleaseMutex(_global_uia_mutex)

# ── Thread-local COM state ───────────────────────────────────────────────────
_tls = threading.local()

def _com_init():
    """Initialize COM in STA for this thread if not already done."""
    if not getattr(_tls, "com_initialized", False):
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        _tls.com_initialized = True

def _handle(conn: socket.socket):
    _com_init()
    try:
        conn.settimeout(30)
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
        button   = req.get("button", "left") or "left"
        monitor  = int(req.get("monitor", 0))

        # Build a simple namespace to reuse dispatch()
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
        args.button   = button
        args.monitor  = monitor

        _acquire_global_uia()
        try:
            with _lock:
                result = dt.dispatch(args)
        finally:
            _release_global_uia()

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
    srv.listen(16)   # increased from 8 → 16 for burst tolerance
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
