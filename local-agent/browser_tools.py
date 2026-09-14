"""browser_tools.py - CDP Edge automation (compact P0 fix)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import os, json, time, socket, argparse, threading, subprocess, urllib.request
try:
    import keyboard
    keyboard.add_hotkey("ctrl+alt+b", lambda: (print(json.dumps({"ok": False, "error": "stopped"})), os._exit(1)))
except Exception:
    pass
from playwright.sync_api import sync_playwright

DAEMON_PORT, CDP_URL, CDP_PORT = 19879, "http://127.0.0.1:9222", 9222
USER_DATA_DIR = os.environ.get("VOILA_BROWSER_PROFILE", r"C:\tmp\ai_browser_profile")
_active_page_id = None

def _cdp_ok(t=1.0):
    try:
        with urllib.request.urlopen(CDP_URL + "/json/version", timeout=t) as r:
            return r.status == 200
    except Exception:
        return False

def _edge():
    for c in [os.environ.get("VOILA_EDGE_PATH", ""),
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]:
        if c and os.path.isfile(c):
            return c
    return r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def _launch(url="https://www.google.com"):
    if _cdp_ok():
        return
    if not url or url.lower() in ("about:blank", "blank"):
        url = "https://www.google.com"
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    args = [_edge(), f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={USER_DATA_DIR}",
            "--no-first-run", "--no-default-browser-check", url]
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)

def _connect(p, hint=None):
    if not _cdp_ok(0.8):
        _launch(hint or "https://www.google.com")
    err = None
    for i in range(40):
        try:
            if _cdp_ok(0.5):
                return p.chromium.connect_over_cdp(CDP_URL), "cdp"
        except Exception as e:
            err = e
        if i == 5 and not _cdp_ok():
            _launch(hint or "https://www.google.com")
        time.sleep(0.5)
    raise RuntimeError(f"CDP connect failed: {err}")

def _info(page):
    u = t = ""
    try: u = page.url or ""
    except Exception: pass
    try: t = page.title() or ""
    except Exception: pass
    return {"url": u, "title": t}

def _ok(a, page, **k):
    d = {"ok": True, "action": a, **_info(page)}; d.update(k); return d

def _err(a, msg, page=None, **k):
    d = {"ok": False, "action": a, "error": msg}
    if page is not None: d.update(_info(page))
    d.update(k); return d

def _page(browser):
    global _active_page_id
    ctxs = browser.contexts
    if not ctxs:
        p = browser.new_context().new_page(); _active_page_id = id(p); return p
    ctx, pages = ctxs[0], list(ctxs[0].pages)
    if _active_page_id:
        for p in pages:
            if id(p) == _active_page_id: return p
    for p in pages:
        try:
            u = (p.url or "").lower()
            if u and u not in ("about:blank", "chrome://newtab/", "edge://newtab/"):
                _active_page_id = id(p); return p
        except Exception: pass
    if pages:
        _active_page_id = id(pages[-1]); return pages[-1]
    p = ctx.new_page(); _active_page_id = id(p); return p

def _handle(browser, args):
    global _active_page_id
    action = (args.get("action") or "").strip().lower()
    page = _page(browser)
    wt = int(args.get("wait_time") or 1000)
    try:
        if action == "goto":
            url = (args.get("url") or "").strip()
            if not url: return _err(action, "url required", page)
            if url.lower() in ("about:blank", "blank"):
                return _err(action, "Refusing about:blank — use real https URL", page)
            if not url.startswith("http"): url = "https://" + url
            page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try: page.wait_for_timeout(min(wt, 3000))
            except Exception: pass
            return _ok(action, page, navigated_to=url)
        if action == "click":
            sel = args.get("selector")
            if not sel: return _err(action, "selector required", page)
            page.locator(sel).first.click(timeout=20000)
            return _ok(action, page, selector=sel)
        if action == "type":
            sel, val = args.get("selector"), args.get("value")
            if not sel or val is None: return _err(action, "selector and value required", page)
            page.locator(sel).first.fill(str(val), timeout=20000)
            return _ok(action, page, selector=sel)
        if action == "press":
            val, sel = args.get("value") or args.get("key"), args.get("selector")
            if not val: return _err(action, "value (key) required", page)
            if sel: page.locator(sel).first.press(val, timeout=10000)
            else: page.keyboard.press(val)
            return _ok(action, page, key=val)
        if action == "scroll":
            val = (args.get("value") or "down").lower()
            if val in ("up", "pageup"): page.evaluate("window.scrollBy(0,-window.innerHeight)")
            elif val in ("down", "pagedown"): page.evaluate("window.scrollBy(0,window.innerHeight)")
            else:
                try: page.evaluate(f"window.scrollBy(0,{int(val)})")
                except Exception: page.evaluate("window.scrollBy(0,window.innerHeight)")
            return _ok(action, page)
        if action == "new_tab":
            url = (args.get("url") or "").strip()
            if not url or url.lower() in ("about:blank", "blank"): url = "https://www.google.com"
            if not url.startswith("http"): url = "https://" + url
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            np = ctx.new_page(); _active_page_id = id(np)
            np.goto(url, timeout=45000, wait_until="domcontentloaded")
            return _ok(action, np, navigated_to=url)
        if action == "list_tabs":
            tabs = []
            if browser.contexts:
                for i, p in enumerate(browser.contexts[0].pages):
                    tabs.append({"index": i, **_info(p)})
            return {"ok": True, "action": action, "tabs": tabs}
        if action == "close_tab":
            pages = browser.contexts[0].pages if browser.contexts else []
            if len(pages) <= 1: return _err(action, "refusing to close last tab", page)
            page.close()
            rem = browser.contexts[0].pages
            _active_page_id = id(rem[-1]) if rem else None
            return {"ok": True, "action": action, "tabs_left": len(rem)}
        if action == "switch_tab":
            val = str(args.get("value") or args.get("index") or "0")
            try:
                i = int(val)
                pages = browser.contexts[0].pages if browser.contexts else []
                if i < 0 or i >= len(pages): return _err(action, "index out of range", page)
                _active_page_id = id(pages[i]); pages[i].bring_to_front()
                return _ok(action, pages[i], tab_index=i)
            except ValueError:
                for ctx in browser.contexts:
                    for p in ctx.pages:
                        if val.lower() in (p.url or "").lower() or val.lower() in (p.title() or "").lower():
                            _active_page_id = id(p); p.bring_to_front(); return _ok(action, p)
                return _err(action, f"no tab match: {val}", page)
        if action == "scrape":
            sel = args.get("selector")
            if sel: return _ok(action, page, texts=page.locator(sel).all_inner_texts()[:50])
            return _ok(action, page, text=(page.inner_text("body") or "")[:8000])
        if action in ("snapshot", "extract_links"):
            links = page.evaluate("""() => Array.from(document.querySelectorAll('a,button,input,[role=button]')).slice(0,300).map(el => {
              const text=(el.innerText||el.value||el.getAttribute('aria-label')||'').trim().slice(0,120);
              let sel=el.id?'#'+el.id:el.tagName.toLowerCase();
              return {type:el.tagName.toLowerCase(), text, selector:sel};
            }).filter(x=>x.text.length>0).slice(0,75)""")
            return _ok(action, page, elements=links)
        if action == "eval":
            expr = args.get("value")
            if not expr: return _err(action, "value required", page)
            return _ok(action, page, result=page.evaluate(expr))
        if action == "ensure":
            return _ok(action, page, cdp=True)
        return _err(action or "unknown", f"Unknown action: {action}", page)
    except Exception as e:
        return _err(action, str(e), page)

def _daemon(hint=None):
    with sync_playwright() as p:
        browser, mode = _connect(p, hint)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try: s.bind(("127.0.0.1", DAEMON_PORT))
        except OSError: return
        s.listen(5); s.settimeout(180)
        while True:
            try: conn, _ = s.accept()
            except socket.timeout: break
            try:
                raw = b""
                while b"\n" not in raw:
                    ch = conn.recv(65536)
                    if not ch: break
                    raw += ch
                req = json.loads(raw.strip() or b"{}")
                if not browser.is_connected():
                    browser, mode = _connect(p, req.get("url"))
                res = _handle(browser, req); res["connection"] = mode
                conn.sendall((json.dumps(res, default=str) + "\n").encode())
            except Exception as e:
                try: conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
                except Exception: pass
            finally:
                try: conn.close()
                except Exception: pass
        try: browser.close()
        except Exception: pass
        try: s.close()
        except Exception: pass

def _send(req):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(60); sock.connect(("127.0.0.1", DAEMON_PORT))
    sock.sendall((json.dumps(req) + "\n").encode())
    raw = b""
    while b"\n" not in raw:
        ch = sock.recv(65536)
        if not ch: break
        raw += ch
    sock.close()
    return json.loads(raw.strip().decode("utf-8", errors="replace"))

def _running():
    try:
        s = socket.create_connection(("127.0.0.1", DAEMON_PORT), timeout=0.4); s.close(); return True
    except OSError: return False

def _start(hint=None):
    threading.Thread(target=_daemon, args=(hint,), daemon=True).start()
    for _ in range(50):
        time.sleep(0.2)
        if _running(): return
    raise RuntimeError("daemon failed to start")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"); ap.add_argument("--action", required=True)
    ap.add_argument("--selector"); ap.add_argument("--value"); ap.add_argument("--wait_time", type=int, default=1000)
    a = ap.parse_args()
    req = {"action": a.action, "url": a.url, "selector": a.selector, "value": a.value, "wait_time": a.wait_time}
    try:
        if not _running():
            _start(a.url if a.action in ("goto", "new_tab") else None)
        r = _send(req)
        print(json.dumps(r, default=str))
        if isinstance(r, dict) and r.get("ok") is False: sys.exit(2)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "action": a.action})); sys.exit(1)

if __name__ == "__main__":
    main()
