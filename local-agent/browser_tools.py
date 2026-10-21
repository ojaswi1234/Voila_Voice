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

import re, urllib.parse, hashlib

DAEMON_PORT, CDP_URL, CDP_PORT = 19879, "http://127.0.0.1:9222", 9222
USER_DATA_DIR = os.environ.get("VOILA_BROWSER_PROFILE", r"C:\tmp\ai_browser_profile")
_active_tab_index = 0

_NOISE_RE = re.compile(r"time|clock|counter|spinner|timestamp|\b\d{1,2}:\d{2}(?::\d{2})?\b", re.IGNORECASE)

def clean_url_for_sig(url: str) -> str:
    """Strip churn-inducing query strings or hash fragments for deterministic signatures."""
    try:
        parsed = urllib.parse.urlparse(url or "")
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return url or ""

def build_dom_signature(url: str, elements: list) -> str:
    """Build a deterministic, noise-resilient 16-character MD5 DOM signature."""
    clean_u = clean_url_for_sig(url)
    tuples = []
    for el in elements:
        name = str(el.get("name") or "").strip()
        testid = str(el.get("testid") or "").strip()
        role = str(el.get("role") or "").strip()
        href = str(el.get("href") or el.get("suggested_locator") or "").strip()

        # Filter out noisy ephemeral widgets (clocks, counters, spinners, timestamps)
        if _NOISE_RE.search(name) or _NOISE_RE.search(testid):
            continue

        tuples.append((role, name[:40], testid, clean_url_for_sig(href)))

    tuples.sort()
    sig_content = f"{clean_u}|{len(tuples)}|" + "|".join(f"{r}:{n}:{t}:{h[:20]}" for r, n, t, h in tuples[:50])
    return hashlib.md5(sig_content.encode('utf-8')).hexdigest()[:16]

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
    raise RuntimeError(f"cdp_unavailable: Microsoft Edge remote debugging port {CDP_PORT} is unavailable ({err}).")

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

def _setup_dialog(page, policy="accept"):
    try:
        if getattr(page, "_voila_dialog_set", False):
            return
        page._voila_dialog_set = True
        page.on("dialog", lambda d: d.accept() if policy == "accept" else d.dismiss())
    except Exception:
        pass

def _page(browser):
    global _active_tab_index
    ctxs = browser.contexts
    if not ctxs:
        p = browser.new_context().new_page()
        _active_tab_index = 0
        _setup_dialog(p)
        return p
    pages = ctxs[0].pages
    if not pages:
        p = ctxs[0].new_page()
        _active_tab_index = 0
        _setup_dialog(p)
        return p
    if _active_tab_index < 0 or _active_tab_index >= len(pages):
        _active_tab_index = len(pages) - 1
    p = pages[_active_tab_index]
    _setup_dialog(p)
    return p


def _get_loc(page, sel):
    s = (sel or "").strip()
    if not s:
        return page.locator("body")

    # 1. Structured locator syntax:
    # role=button[name="Submit"] or role=button;name=Submit
    if s.lower().startswith("role="):
        rest = s[5:].strip()
        name = ""
        role = rest
        if "[" in rest and "name=" in rest:
            role = rest.split("[")[0].strip()
            name_part = rest.split("name=")[1].rstrip("]").strip(' "\'')
            name = name_part
        elif ";" in rest and "name=" in rest:
            parts = rest.split(";")
            role = parts[0].strip()
            for p in parts[1:]:
                if p.strip().startswith("name="):
                    name = p.strip()[5:].strip(' "\'')
        try:
            if name:
                loc = page.get_by_role(role, name=name)
            else:
                loc = page.get_by_role(role)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

    if s.lower().startswith("label="):
        lbl = s[6:].strip(' "\'')
        try:
            loc = page.get_by_label(lbl)
            if loc.count() > 0: return loc.first
        except Exception: pass

    if s.lower().startswith("placeholder="):
        ph = s[12:].strip(' "\'')
        try:
            loc = page.get_by_placeholder(ph)
            if loc.count() > 0: return loc.first
        except Exception: pass

    if s.lower().startswith("testid="):
        tid = s[7:].strip(' "\'')
        try:
            loc = page.get_by_test_id(tid)
            if loc.count() > 0: return loc.first
        except Exception: pass

    if s.lower().startswith("text="):
        txt = s[5:].strip(' "\'')
        try:
            loc = page.get_by_text(txt, exact=False)
            if loc.count() > 0: return loc.first
        except Exception: pass

    # 2. Try standard CSS / XPath locator directly
    try:
        loc = page.locator(s)
        if loc.count() > 0: return loc.first
    except Exception:
        pass
        
    # 3. Check text or accessible roles
    try:
        loc_text = page.get_by_text(s, exact=False)
        if loc_text.count() > 0: return loc_text.first
    except Exception:
        pass

    try:
        loc_btn = page.get_by_role("button", name=s)
        if loc_btn.count() > 0: return loc_btn.first
        loc_link = page.get_by_role("link", name=s)
        if loc_link.count() > 0: return loc_link.first
    except Exception:
        pass

    # 4. Check inside iframes
    for frame in page.frames:
        try:
            floc = frame.locator(s).first
            if floc.count() > 0: return floc
        except Exception:
            pass
        try:
            floc_text = frame.get_by_text(s, exact=False).first
            if floc_text.count() > 0: return floc_text
        except Exception:
            pass
            
    return page.locator(s).first

def _handle(browser, args):
    global _active_tab_index
    action = (args.get("action") or "").strip().lower()
    page = _page(browser)
    wt = int(args.get("wait_time") or 1000)
    try:
        if action == "health":
            return _ok(action, page, cdp_ok=_cdp_ok(0.5))

        if action == "goto":
            url = (args.get("url") or "").strip()
            if not url: return _err(action, "url required", page)
            if url.lower() in ("about:blank", "blank"):
                return _err(action, "Refusing about:blank — use real https URL", page)
            if not url.startswith("http"): url = "https://" + url
            # Guard against redundant search engine browsing that wastes tokens
            u_lower = url.lower()
            if any(engine in u_lower for engine in ("google.com/search", "bing.com/search", "duckduckgo.com/?q", "search.yahoo.com/search")):
                return _err(action, "Search engine URL blocked in browser_automation to prevent token waste. Use the 'web_research' tool instead, or MCP tools for GitHub/YouTube/Notion/Gmail.", page)
            wait_networkidle = args.get("wait_networkidle") in (True, "true", "1", 1)
            wait_until_state = "networkidle" if wait_networkidle else "domcontentloaded"
            page.goto(url, timeout=45000, wait_until=wait_until_state)
            try: page.wait_for_timeout(min(wt, 3000))
            except Exception: pass
            return _ok(action, page, navigated_to=url, extract_hint=True)

        if action == "wait_for":
            target_sel = args.get("selector")
            target_url = args.get("url")
            target_text = args.get("text") or args.get("value")
            target_state = args.get("state") or "visible"
            timeout = int(args.get("timeout_ms") or args.get("wait_time") or 10000)
            
            try:
                if target_url:
                    page.wait_for_url(target_url, timeout=timeout)
                    return _ok(action, page, waited_for=f"url:{target_url}")
                elif target_sel:
                    loc = _get_loc(page, target_sel)
                    loc.wait_for(state=target_state if target_state in ("attached", "visible", "hidden") else "visible", timeout=timeout)
                    return _ok(action, page, waited_for=f"selector:{target_sel}")
                elif target_text:
                    loc = page.get_by_text(target_text, exact=False)
                    loc.first.wait_for(state="visible", timeout=timeout)
                    return _ok(action, page, waited_for=f"text:{target_text}")
                elif target_state in ("load", "domcontentloaded", "networkidle"):
                    page.wait_for_load_state(target_state, timeout=timeout)
                    return _ok(action, page, waited_for=f"state:{target_state}")
                else:
                    page.wait_for_timeout(min(timeout, 5000))
                    return _ok(action, page, waited_for=f"timeout:{timeout}ms")
            except Exception as e:
                return _err(action, f"wait_for failed or timed out: {e}", page)

        if action == "click":
            sel = args.get("selector")
            if not sel: return _err(action, "selector required", page)
            loc = _get_loc(page, sel)
            click_path = "normal"
            warning = None
            s_sel = str(sel)
            if len(s_sel) > 80 or s_sel.count("nth-child") > 1:
                warning = "brittle_selector_warning"
            try:
                # Lean on locator auto-wait (visible, stable, receives events)
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed(timeout=2000)
                loc.click(timeout=4000)
                click_path = "normal"
            except Exception as e:
                # Fallback 1: forced click if obscured by sticky headers/modals
                try: 
                    loc.click(force=True, timeout=2000)
                    click_path = "force"
                except Exception:
                    # Fallback 2: direct JS click dispatch
                    try:
                        loc.evaluate("el => el.click()")
                        click_path = "js"
                    except Exception:
                        return _err(action, f"Click failed on {sel!r}: {e}", page, selector=sel, click_path="failed", warning=warning)
            return _ok(action, page, selector=sel, click_path=click_path, warning=warning)

        if action == "type":
            sel, val = args.get("selector"), args.get("value")
            if not sel or val is None: return _err(action, "selector and value required", page)
            loc = _get_loc(page, sel)
            try:
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed(timeout=2000)
                try:
                    tag = loc.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "select":
                        loc.select_option(label=str(val), timeout=4000)
                    elif tag == "input" and loc.evaluate("el => el.type.toLowerCase()") in ("checkbox", "radio"):
                        if str(val).lower() in ("true", "1", "yes", "on"): loc.check(timeout=4000)
                        else: loc.uncheck(timeout=4000)
                    else:
                        loc.fill(str(val), timeout=4000)
                except Exception:
                    loc.fill(str(val), timeout=4000)
            except Exception as e:
                try: loc.fill(str(val), force=True, timeout=2000)
                except Exception: return _err(action, f"Type failed on {sel!r}: {e}", page)
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
            settle_ms = int(os.environ.get("VOILA_BROWSER_SETTLE_MS", "150"))
            if settle_ms > 0:
                try: page.wait_for_timeout(settle_ms)
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
                
                const isInteractive = (el) => {
                    const tag = el.tagName.toLowerCase();
                    if (['a', 'button', 'input', 'textarea', 'select', 'summary', 'label'].includes(tag)) return true;
                    if (el.isContentEditable) return true;
                    const role = el.getAttribute('role');
                    if (role && ['button', 'link', 'menuitem', 'tab', 'option', 'combobox', 'switch', 'checkbox', 'radio', 'treeitem'].includes(role)) return true;
                    if (el.hasAttribute('tabindex') && el.getAttribute('tabindex') !== '-1') return true;
                    const cls = (el.className || '').toString().toLowerCase();
                    if (cls.includes('btn') || cls.includes('button') || cls.includes('toggle') || cls.includes('filter') || cls.includes('dropdown')) {
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
                    const tag = el.tagName.toLowerCase();
                    let role = el.getAttribute('role') || (tag === 'a' ? 'link' : (['button', 'input', 'textarea', 'select'].includes(tag) ? tag : 'generic'));
                    if (tag === 'input' && el.type) {
                        if (['button', 'submit', 'reset'].includes(el.type)) role = 'button';
                        else if (['checkbox', 'radio'].includes(el.type)) role = el.type;
                        else role = 'textbox';
                    }

                    let text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
                    let testId = el.getAttribute('data-testid') || el.getAttribute('data-test-id') || el.getAttribute('data-qa') || '';
                    let placeholder = el.getAttribute('placeholder') || '';
                    let ariaLabel = el.getAttribute('aria-label') || '';
                    const isDisabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';

                    if (!text && tag === 'input' && el.type === 'submit') { text = "Submit"; }
                    if (!text && tag === 'input' && el.type === 'text') { text = "Text Input"; }
                    if (!text && tag === 'input' && el.type === 'password') { text = "Password"; }
                    if (!text && tag === 'select') { text = "Dropdown Selection"; }
                    if (!text && tag === 'textarea') { text = "Text Area"; }
                    
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
                        } else if (role === 'button' || tag === 'button') {
                            text = "[Unlabeled Button]";
                        }
                    }
                    
                    text = text.replace(/\\s+/g, ' ').slice(0, 100);
                    
                    let suggested = '';
                    if (testId) {
                        suggested = 'testid=' + testId;
                    } else if (ariaLabel && role !== 'generic') {
                        suggested = 'role=' + role + '[name="' + ariaLabel.replace(/"/g, '') + '"]';
                    } else if (text && ['button', 'link', 'tab', 'menuitem'].includes(role)) {
                        suggested = 'role=' + role + '[name="' + text.replace(/"/g, '') + '"]';
                    } else if (placeholder) {
                        suggested = 'placeholder="' + placeholder.replace(/"/g, '') + '"';
                    } else if (text && text.length < 40) {
                        suggested = 'text="' + text.replace(/"/g, '') + '"';
                    } else if (el.id && /^[A-Za-z][A-Za-z0-9_-]*$/.test(el.id)) {
                        suggested = '#' + el.id;
                    } else {
                        if (!el.hasAttribute('data-ai-id')) {
                            aiIdCounter++;
                            el.setAttribute('data-ai-id', 'ai-btn-' + aiIdCounter);
                        }
                        suggested = '[data-ai-id="' + el.getAttribute('data-ai-id') + '"]';
                    }
                    window._aiIdCounter = aiIdCounter;
                    
                    return {
                        role: role,
                        name: text,
                        tag: tag,
                        testid: testId,
                        placeholder: placeholder,
                        suggested_locator: suggested,
                        selector: suggested,
                        disabled: isDisabled
                    };
                }).filter(x => x.name.length > 0 || ['input', 'textarea', 'select'].includes(x.tag)).slice(0, 100);
            }"""

            # Extract from main page and all iframes
            for frame in page.frames:
                try:
                    frame_links = frame.evaluate(js_script)
                    if frame_links:
                        all_links.extend(frame_links)
                except Exception:
                    continue
            
            # Deduplicate and cap to 100
            seen_selectors = set()
            unique_links = []
            for link in all_links:
                if link['selector'] not in seen_selectors:
                    seen_selectors.add(link['selector'])
                    unique_links.append(link)
            
            # Generate 16-char content signature hash for loop detection
            dom_signature = build_dom_signature(page.url, unique_links)

            return _ok(action, page, elements=unique_links[:100], count=len(unique_links[:100]), signature=dom_signature)

        if action == "upload":
            sel, val = args.get("selector"), args.get("value")
            if not val: return _err(action, "value (file path) required", page)
            if not os.path.exists(val): return _err(action, f"File does not exist: {val}", page)
            
            try:
                loc = _get_loc(page, sel) if sel else None
                # 1. Try direct set_input_files on input[type=file]
                if loc and loc.count() > 0:
                    try:
                        tag = loc.evaluate("el => el.tagName.toLowerCase()")
                        type_attr = loc.evaluate("el => el.type ? el.type.toLowerCase() : ''")
                        if tag == "input" and type_attr == "file":
                            loc.set_input_files(val, timeout=5000)
                            return _ok(action, page, message=f"Uploaded {val} via set_input_files", selector=sel)
                    except Exception:
                        pass
                
                # 2. Intercept file chooser dialog
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    if loc: loc.click(timeout=3000)
                    else: page.locator("input[type=file]").first.click(timeout=3000)
                file_chooser = fc_info.value
                file_chooser.set_files(val)
                return _ok(action, page, message=f"Uploaded {val} via file_chooser intercept", selector=sel)
            except Exception as e:
                return _err(action, "needs_desktop_assist", page, message=f"Upload error: {e}. Note: If an OS-native file dialog opened, desktop automation bridge is required.")
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
    ap.add_argument("--wait-networkidle", action="store_true", dest="wait_networkidle")
    a = ap.parse_args()
    if a.serve_daemon:
        _daemon(a.url)
        return
    if not a.action:
        print(json.dumps({"ok": False, "error": "action required"})); sys.exit(1)
    req = {"action": a.action, "url": a.url, "selector": a.selector, "value": a.value, "wait_time": a.wait_time, "wait_networkidle": a.wait_networkidle}
    try:
        if not _running():
            _start_detached(a.url if a.action in ("goto", "new_tab") else None)
        r = _send(req)
        print(json.dumps(r, default=str))
        if isinstance(r, dict) and r.get("ok") is False: sys.exit(2)
    except Exception as e:
        err_msg = str(e)
        err_code = "cdp_unavailable" if "cdp_unavailable" in err_msg or "failed to start" in err_msg else "browser_error"
        print(json.dumps({"ok": False, "error": err_code, "message": err_msg, "action": a.action}))
        sys.exit(1)

if __name__ == "__main__":
    main()
