"""browser_tools.py - CDP Edge automation (compact P0 fix)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import os, json, time, socket, argparse, subprocess, urllib.request
try:
    import keyboard
    keyboard.add_hotkey("ctrl+alt+b", lambda: (print(json.dumps({"ok": False, "error": "stopped"})), os._exit(1)))
except Exception:
    pass
from playwright.sync_api import sync_playwright

DAEMON_PORT, CDP_URL, CDP_PORT = 19879, "http://127.0.0.1:9222", 9222
USER_DATA_DIR = os.environ.get("VOILA_BROWSER_PROFILE", r"C:\tmp\ai_browser_profile")
_active_tab_index = 0

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
    global _active_tab_index
    d = {"ok": True, "action": a, **_info(page)}; d.update(k)
    try:
        if hasattr(page, 'context') and page.context:
            d["tab_index"] = _active_tab_index
            d["tabs_count"] = len(page.context.pages)
    except Exception:
        pass
    return d

def _err(a, msg, page=None, **k):
    global _active_tab_index
    d = {"ok": False, "action": a, "error": msg}
    if page is not None: d.update(_info(page))
    try:
        if page is not None and hasattr(page, 'context') and page.context:
            d["tab_index"] = _active_tab_index
            d["tabs_count"] = len(page.context.pages)
    except Exception:
        pass
    d.update(k); return d

def _page(browser):
    global _active_tab_index
    ctxs = browser.contexts
    if not ctxs:
        p = browser.new_context().new_page()
        _active_tab_index = 0
        return p
    pages = ctxs[0].pages
    if not pages:
        p = ctxs[0].new_page()
        _active_tab_index = 0
        return p
    if _active_tab_index < 0 or _active_tab_index >= len(pages):
        _active_tab_index = len(pages) - 1
    return pages[_active_tab_index]


def _get_loc(page, sel):
    loc = _get_loc(page, sel)
    try:
        if loc.count() > 0: return loc
    except Exception:
        pass
    for frame in page.frames:
        try:
            floc = frame.locator(sel).first
            if floc.count() > 0: return floc
        except Exception:
            pass
    return loc

def _handle(browser, args):
    global _active_tab_index
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
            loc = _get_loc(page, sel)
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.click(timeout=5000)
            except Exception as e:
                # Fallback to forced click if obscured by sticky headers/modals
                try: loc.click(force=True, timeout=2000)
                except Exception: raise e
            return _ok(action, page, selector=sel)
        if action == "type":
            sel, val = args.get("selector"), args.get("value")
            if not sel or val is None: return _err(action, "selector and value required", page)
            loc = _get_loc(page, sel)
            try:
                loc.scroll_into_view_if_needed(timeout=3000)
                try:
                    tag = loc.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        loc.select_option(label=str(val), timeout=5000)
                    elif tag == "input" and loc.evaluate("el => el.type.toLowerCase()") in ("checkbox", "radio"):
                        if str(val).lower() in ("true", "1", "yes", "on"): loc.check(timeout=5000)
                        else: loc.uncheck(timeout=5000)
                    else:
                        loc.fill(str(val), timeout=5000)
                except Exception:
                    loc.fill(str(val), timeout=5000)
            except Exception as e:
                try: loc.fill(str(val), force=True, timeout=2000)
                except Exception: raise e
            return _ok(action, page, selector=sel)
        if action == "press":
            val, sel = args.get("value") or args.get("key"), args.get("selector")
            if not val: return _err(action, "value (key) required", page)
            if sel: 
                loc = _get_loc(page, sel)
                loc.scroll_into_view_if_needed(timeout=2000)
                loc.press(val, timeout=5000)
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
        if action == "hover":
            sel = args.get("selector")
            if not sel: return _err(action, "selector required", page)
            loc = _get_loc(page, sel)
            loc.scroll_into_view_if_needed(timeout=3000)
            loc.hover(timeout=5000)
            return _ok(action, page, selector=sel)

        if action == "search_word":
            val = args.get("value")
            if not val: return _err(action, "value (search term) required", page)
            
            # Recursive search across main page and frames
            loc = page.locator(f"text={val}")
            count = loc.count()
            if count > 0:
                loc.first.scroll_into_view_if_needed()
                return _ok(action, page, message=f"Found {count} occurrences in main frame, scrolled to first.")
            
            for i, frame in enumerate(page.frames):
                floc = frame.locator(f"text={val}")
                try:
                    fcount = floc.count()
                    if fcount > 0:
                        floc.first.scroll_into_view_if_needed()
                        return _ok(action, page, message=f"Found {fcount} occurrences in iframe {i}, scrolled to first.")
                except Exception: pass
                
            return _ok(action, page, message="Word not found anywhere on the page or in iframes")
        if action == "new_tab":
            url = (args.get("url") or "").strip()
            if not url or url.lower() in ("about:blank", "blank"):
                return _err(action, "Refusing about:blank — use real https URL", page)
            if not url.startswith("http"): url = "https://" + url
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            np = ctx.new_page()
            _active_tab_index = len(ctx.pages) - 1
            np.goto(url, timeout=45000, wait_until="domcontentloaded")
            return _ok(action, np, navigated_to=url)
        if action == "list_tabs":
            tabs = []
            if browser.contexts:
                for i, p in enumerate(browser.contexts[0].pages):
                    tab_info = {"index": i, **_info(p)}
                    if i == _active_tab_index:
                        tab_info["active"] = True
                    tabs.append(tab_info)
            return {"ok": True, "action": action, "tabs": tabs, "tabs_count": len(tabs), "tab_index": _active_tab_index}
        if action == "close_tab":
            pages = browser.contexts[0].pages if browser.contexts else []
            if len(pages) <= 1: return _err(action, "refusing to close last tab", page)
            page.close()
            rem = browser.contexts[0].pages
            if _active_tab_index >= len(rem):
                _active_tab_index = len(rem) - 1
            return {"ok": True, "action": action, "tabs_left": len(rem), "tab_index": _active_tab_index, "tabs_count": len(rem)}
        if action == "switch_tab":
            val = str(args.get("value") or args.get("index") or "0")
            try:
                i = int(val)
                pages = browser.contexts[0].pages if browser.contexts else []
                if i < 0 or i >= len(pages): return _err(action, "index out of range", page)
                _active_tab_index = i
                pages[i].bring_to_front()
                return _ok(action, pages[i], tab_index=i)
            except ValueError:
                for ctx in browser.contexts:
                    for i, p in enumerate(ctx.pages):
                        if val.lower() in (p.url or "").lower() or val.lower() in (p.title() or "").lower():
                            _active_tab_index = i; p.bring_to_front(); return _ok(action, p)
                return _err(action, f"no tab match: {val}", page)
        if action == "scrape":
            sel = args.get("selector")
            if sel: return _ok(action, page, texts=page.locator(sel).all_inner_texts()[:50])
            return _ok(action, page, text=(page.inner_text("body") or "")[:8000])
        if action in ("snapshot", "extract_links", "extract_interactive"):
            try: page.wait_for_timeout(1000) # Give frames & dynamic JS extra time to settle
            except Exception: pass
            
            all_links = []
            
            # Helper JS to extract from a specific frame context, piercing Shadow DOMs
            js_script = """() => {
                let aiIdCounter = window._aiIdCounter || 0;
                
                function getAllElements(root) {
                    let els = [];
                    try {
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
                        let node;
                        while (node = walker.nextNode()) {
                            els.push(node);
                            if (node.shadowRoot) els = els.concat(getAllElements(node.shadowRoot));
                        }
                    } catch(e) {}
                    return els;
                }
                
                const allNodes = getAllElements(document);
                
                // Extremely aggressive interactive element detection for modern web apps (filters, custom dropdowns, toggles)
                const isInteractive = (el) => {
                    const tag = el.tagName.toLowerCase();
                    if (['a', 'button', 'input', 'textarea', 'select', 'summary', 'label'].includes(tag)) return true;
                    if (el.isContentEditable) return true;
                    const role = el.getAttribute('role');
                    if (role && ['button', 'link', 'menuitem', 'tab', 'option', 'combobox', 'switch', 'checkbox', 'radio', 'treeitem'].includes(role)) return true;
                    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
                    const cls = (el.className || '').toString().toLowerCase();
                    if (cls.includes('btn') || cls.includes('button') || cls.includes('toggle') || cls.includes('filter') || cls.includes('dropdown')) {
                        // Only include custom classes if they have click listeners or cursor: pointer
                        const style = window.getComputedStyle(el);
                        if (style.cursor === 'pointer') return true;
                    }
                    return false;
                };
                
                const elements = allNodes.filter(isInteractive);
                
                return elements.filter(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.opacity !== '0' && style.display !== 'none';
                }).slice(0, 300).map(el => {
                    let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                    if (!text && el.tagName === 'INPUT' && el.type === 'submit') { text = "Submit"; }
                    if (!text && el.tagName === 'INPUT' && el.type === 'text') { text = "Text Input"; }
                    if (!text && el.tagName === 'INPUT' && el.type === 'password') { text = "Password"; }
                    if (!text && el.tagName === 'SELECT') { text = "Dropdown Selection"; }
                    if (!text && el.tagName === 'TEXTAREA') { text = "Text Area"; }
                    
                    // Fallback for unlabeled popup close buttons (often just SVGs or X icons in divs)
                    if (!text) {
                        const html = el.innerHTML.toLowerCase();
                        const cls = (el.className || '').toString().toLowerCase();
                        const idStr = (el.id || '').toLowerCase();
                        if (cls.includes('close') || idStr.includes('close') || html.includes('close')) {
                            text = "[Close Button]";
                        } else if (html.includes('<svg') || html.includes('<img')) {
                            if (cls.includes('search') || idStr.includes('search')) text = "[Search Icon]";
                            else if (cls.includes('menu') || idStr.includes('menu')) text = "[Menu Icon]";
                            else text = "[Unlabeled Icon Button]";
                        } else if (el.getAttribute('role') === 'button' || el.tagName === 'BUTTON') {
                            text = "[Unlabeled Button]";
                        }
                    }
                    
                    text = text.replace(/\s+/g, ' ').slice(0, 120);
                    
                    let sel = '';
                    if (el.id && /^[A-Za-z][A-Za-z0-9_-]*$/.test(el.id)) {
                        sel = '#' + el.id;
                    } else {
                        if (!el.hasAttribute('data-ai-id')) {
                            aiIdCounter++;
                            el.setAttribute('data-ai-id', 'ai-btn-' + aiIdCounter);
                        }
                        sel = '[data-ai-id="' + el.getAttribute('data-ai-id') + '"]';
                    }
                    window._aiIdCounter = aiIdCounter;
                    
                    return { type: el.tagName.toLowerCase(), text: text, selector: sel };
                }).filter(x => x.text.length > 0 || ['input', 'textarea', 'select'].includes(x.type)).slice(0, 100);
            }"""

            # Extract from main page and all iframes
            for frame in page.frames:
                try:
                    frame_links = frame.evaluate(js_script)
                    if frame_links:
                        all_links.extend(frame_links)
                except Exception:
                    continue # Ignore cross-origin frame access errors if playwright fails to inject
            
            # Deduplicate and cap to prevent token explosion
            seen_selectors = set()
            unique_links = []
            for link in all_links:
                if link['selector'] not in seen_selectors:
                    seen_selectors.add(link['selector'])
                    unique_links.append(link)
            
            return _ok(action, page, elements=unique_links[:150])
        if action == "upload":
            sel, val = args.get("selector"), args.get("value")
            if not sel or not val: return _err(action, "selector and value (file path) required", page)
            loc = _get_loc(page, sel)
            try:
                import os
                if not os.path.exists(val): return _err(action, f"File does not exist: {val}", page)
                loc.scroll_into_view_if_needed(timeout=3000)
                loc.set_input_files(val, timeout=5000)
                return _ok(action, page, message=f"Uploaded {val}")
            except Exception as e:
                return _err(action, str(e), page)
        if action == "fill_form":
            import json
            val = args.get("value")
            if isinstance(val, str):
                try: val = json.loads(val)
                except Exception: return _err(action, "value must be valid JSON dictionary for fill_form", page)
            if not isinstance(val, dict): return _err(action, "value must be a dictionary", page)
            
            results = {}
            for sel, text_val in val.items():
                try:
                    loc = _get_loc(page, sel)
                    loc.scroll_into_view_if_needed(timeout=2000)
                    try:
                        tag = loc.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "select": loc.select_option(label=str(text_val), timeout=3000)
                        elif tag == "input" and loc.evaluate("el => el.type.toLowerCase()") in ("checkbox", "radio"):
                            if str(text_val).lower() in ("true", "1", "yes", "on"): loc.check(timeout=3000)
                            else: loc.uncheck(timeout=3000)
                        else:
                            loc.fill(str(text_val), timeout=3000)
                    except Exception:
                        loc.fill(str(text_val), timeout=3000)
                    results[sel] = "OK"
                except Exception as e:
                    results[sel] = str(e)
            return _ok(action, page, results=results)
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
        s.listen(5); s.settimeout(600)
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

def _start_detached(hint=None):
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    args = [sys.executable, __file__, "--serve-daemon"]
    if hint:
        args.extend(["--url", hint])
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    for _ in range(50):
        time.sleep(0.2)
        if _running(): return
    raise RuntimeError("daemon failed to start")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--action")
    ap.add_argument("--serve-daemon", action="store_true")
    ap.add_argument("--selector"); ap.add_argument("--value"); ap.add_argument("--wait_time", type=int, default=1000)
    a = ap.parse_args()
    if a.serve_daemon:
        _daemon(a.url)
        return
    if not a.action:
        print(json.dumps({"ok": False, "error": "action required"})); sys.exit(1)
    req = {"action": a.action, "url": a.url, "selector": a.selector, "value": a.value, "wait_time": a.wait_time}
    try:
        if not _running():
            _start_detached(a.url if a.action in ("goto", "new_tab") else None)
        r = _send(req)
        print(json.dumps(r, default=str))
        if isinstance(r, dict) and r.get("ok") is False: sys.exit(2)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e), "action": a.action})); sys.exit(1)

if __name__ == "__main__":
    main()
