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

try:
    from browser_payment_rules import (
        is_payment_url, is_payment_cta, is_payment_field,
        is_pan_number, mask_pan, mask_sensitive, is_payment_eval
    )
except ImportError:
    try:
        from .browser_payment_rules import (
            is_payment_url, is_payment_cta, is_payment_field,
            is_pan_number, mask_pan, mask_sensitive, is_payment_eval
        )
    except Exception:
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from browser_payment_rules import (
            is_payment_url, is_payment_cta, is_payment_field,
            is_pan_number, mask_pan, mask_sensitive, is_payment_eval
        )

_last_observed_url = None
_last_observed_signature = None

DAEMON_PORT, CDP_URL, CDP_PORT = 19879, "http://127.0.0.1:9222", 9222
USER_DATA_DIR = os.environ.get("VOILA_BROWSER_PROFILE", r"C:\tmp\ai_browser_profile")
_active_tab_index = 0

if "VOILA_JOB_ID" not in os.environ:
    os.environ["VOILA_JOB_ID"] = (
        os.environ.get("CONVERSATION_ID")
        or os.environ.get("VOILA_CONV_ID")
        or "default"
    )

_NOISE_RE = re.compile(r"time|clock|counter|spinner|timestamp|ticker|live count|seconds ago|\b\d{1,2}:\d{2}(?::\d{2})?\b", re.IGNORECASE)

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

def _resolve_form_field(page, sel: str):
    """Smart resolver that targets the actual interactive input element for a field.
    Handles labels with 'for', aria-labels, placeholders, nearby inputs, contenteditable, comboboxes, and custom controls.
    """
    s = str(sel or "").strip()
    if not s:
        return page.locator("body")

    # 1. Direct accessible label match
    try:
        loc = page.get_by_label(s, exact=False)
        if loc.count() > 0 and loc.first.is_visible():
            return loc.first
    except Exception:
        pass

    # 2. Try _get_loc
    loc = _get_loc(page, s)

    # 3. Inspect if the returned element is a container/label rather than the actual input
    try:
        if loc.count() > 0:
            el = loc.first
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            is_editable = el.evaluate("el => el.isContentEditable || el.getAttribute('contenteditable') === 'true'")
            role = el.evaluate("el => (el.getAttribute('role') || '').toLowerCase()")

            # If it's already an interactive input element, return it directly
            if tag in ("input", "textarea", "select") or is_editable or role in ("combobox", "textbox", "searchbox", "spinbutton", "checkbox", "switch", "radio", "listbox"):
                return el

            # If it's a <label>, follow the 'for' attribute to find target input ID
            if tag == "label":
                for_id = el.evaluate("el => el.getAttribute('for')")
                if for_id:
                    cand = page.locator(f"#{for_id}").first
                    if cand.count() > 0:
                        return cand

            # Check if this container encloses a fillable child
            nested = el.locator("input, textarea, select, [contenteditable='true'], [role=combobox], [role=textbox]").first
            if nested.count() > 0 and nested.is_visible():
                return nested

            # Check immediate following sibling / nearby input
            try:
                following = el.locator("xpath=following::input[1] | following::textarea[1] | following::select[1] | following::*[@contenteditable='true'][1]").first
                if following.count() > 0 and following.is_visible():
                    return following
            except Exception:
                pass
    except Exception:
        pass

    return loc

def _smart_fill_element(page, loc, val, timeout: int = 4000) -> dict:
    """Smart fill helper handling:
    - Native inputs & textareas (with auto-clear, type, and verification)
    - Native <select> (by label, value, or index)
    - Custom comboboxes / select dropdowns (Radix, MUI, AntD, React-Select)
    - Checkboxes & custom ARIA switches
    - Contenteditable / Rich Text editors (Notion, Google Docs, Slack, Jira)
    - Date / time / color / range inputs
    """
    loc.wait_for(state="visible", timeout=timeout)
    loc.scroll_into_view_if_needed(timeout=2000)

    tag = loc.evaluate("el => el.tagName.toLowerCase()")
    role = loc.evaluate("el => (el.getAttribute('role') || '').toLowerCase()")
    input_type = loc.evaluate("el => (el.getAttribute('type') || '').toLowerCase()") if tag == "input" else ""
    is_contenteditable = loc.evaluate("el => el.isContentEditable || el.getAttribute('contenteditable') === 'true'")

    # 1. Native Select
    if tag == "select":
        s_val = str(val)
        try:
            loc.select_option(label=s_val, timeout=timeout)
            return {"method": "select_label", "value": s_val}
        except Exception:
            try:
                loc.select_option(value=s_val, timeout=timeout)
                return {"method": "select_value", "value": s_val}
            except Exception:
                if s_val.isdigit():
                    loc.select_option(index=int(s_val), timeout=timeout)
                    return {"method": "select_index", "value": s_val}
                raise

    # 2. Checkboxes and Switches (Native or ARIA)
    if input_type in ("checkbox", "radio") or role in ("checkbox", "switch", "radio"):
        should_check = str(val).lower() in ("true", "1", "yes", "on", "checked")
        if input_type in ("checkbox", "radio"):
            if should_check: loc.check(timeout=timeout)
            else: loc.uncheck(timeout=timeout)
        else:
            curr_checked = loc.evaluate("el => el.getAttribute('aria-checked') === 'true'")
            if curr_checked != should_check:
                loc.click(timeout=timeout)
        return {"method": "check" if should_check else "uncheck", "value": should_check}

    # 3. Custom Combobox / Accessible Dropdown (Radix, MUI, AntD, Select2)
    if role == "combobox" or (tag == "div" and loc.evaluate("el => el.getAttribute('aria-haspopup') === 'listbox'")):
        s_val = str(val)
        try:
            if tag == "input":
                loc.fill(s_val, timeout=2000)
                page.keyboard.press("Enter")
                return {"method": "combobox_input_enter", "value": s_val}
        except Exception:
            pass
        loc.click(timeout=2000)
        time.sleep(0.15)
        option_loc = page.get_by_role("option", name=s_val)
        if option_loc.count() > 0:
            option_loc.first.click(timeout=3000)
            return {"method": "combobox_option_click", "value": s_val}
        else:
            page.keyboard.type(s_val)
            time.sleep(0.1)
            page.keyboard.press("Enter")
            return {"method": "combobox_type_enter", "value": s_val}

    # 4. Contenteditable / Rich Text editors (Notion, Google Docs, Slack, Jira)
    if is_contenteditable:
        s_val = str(val)
        loc.click(timeout=timeout)
        loc.evaluate("(el, v) => { el.focus(); document.execCommand('selectAll', false, null); document.execCommand('insertText', false, v); }", s_val)
        return {"method": "contenteditable_insert", "value": s_val}

    # 5. Date / Time inputs
    if input_type in ("date", "time", "datetime-local", "month"):
        s_val = str(val)
        loc.fill(s_val, timeout=timeout)
        loc.evaluate("el => { el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }")
        return {"method": "date_fill", "value": s_val}

    # 6. Standard Input / Textarea
    s_val = str(val)
    fill_ok = False
    try:
        loc.fill(s_val, timeout=timeout)
        fill_ok = True
    except Exception:
        loc.click(force=True, timeout=2000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(s_val, delay=10)
        fill_ok = True

    current_val = ""
    try:
        current_val = loc.input_value(timeout=1000) if tag in ("input", "textarea") else ""
    except Exception:
        pass

    return {"method": "fill", "value": s_val, "verified": (current_val == s_val if current_val else fill_ok)}

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
            # Payment guardrail
            m_url, r_url = is_payment_url(url)
            if m_url:
                return _err(action, "payment_blocked", page, message=f"Navigation to payment/checkout URL ({r_url}) is blocked by safety guardrails. Please complete payments manually in your browser.", matched_rule=r_url)
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

            # Payment guardrail on selector and page
            on_pay, _ = is_payment_url(page.url)
            m_cta, r_cta = is_payment_cta(sel)
            if m_cta:
                return _err(action, "payment_blocked", page, message=f"Clicking payment control '{r_cta}' is blocked by payment guardrails. Please complete payments manually.", matched_rule=r_cta)
            m_fld, r_fld = is_payment_field(sel, on_pay)
            if m_fld:
                return _err(action, "payment_blocked", page, message=f"Interacting with payment field '{r_fld}' is blocked by payment guardrails.", matched_rule=r_fld)

            loc = _get_loc(page, sel)

            # Inspect target element attributes for payment indicators
            try:
                elem_info = loc.evaluate("el => ({ text: (el.innerText || el.value || '').trim(), aria: el.getAttribute('aria-label') || '', name: el.getAttribute('name') || '', id: el.id || '' })")
                comb = f"{elem_info.get('text', '')} {elem_info.get('aria', '')} {elem_info.get('name', '')} {elem_info.get('id', '')}"
                m_c, r_c = is_payment_cta(comb)
                if m_c:
                    return _err(action, "payment_blocked", page, message=f"Clicking payment button '{r_c}' is blocked by payment guardrails. Please complete payments manually.", matched_rule=r_c)
                m_f, r_f = is_payment_field(comb, on_pay)
                if m_f:
                    return _err(action, "payment_blocked", page, message=f"Interacting with payment control '{r_f}' is blocked by payment guardrails.", matched_rule=r_f)
            except Exception:
                pass
            click_path = "normal"
            warning = None
            s_sel = str(sel)
            if len(s_sel) > 80 or s_sel.count("nth-child") > 1 or s_sel.count("nth-of-type") > 1:
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

            # Payment guardrails
            if is_pan_number(str(val)):
                return _err(action, "payment_blocked", page, message="Entering payment card numbers (PAN) is blocked by safety guardrails.", matched_rule="pan_number_pattern")
            on_pay, _ = is_payment_url(page.url)
            m_fld, r_fld = is_payment_field(sel, on_pay)
            if m_fld:
                return _err(action, "payment_blocked", page, message=f"Entering details into payment field '{r_fld}' is blocked by payment guardrails.", matched_rule=r_fld)

            loc = _resolve_form_field(page, sel)
            try:
                f_info = loc.evaluate("el => ({ name: el.getAttribute('name') || '', id: el.id || '', auto: el.getAttribute('autocomplete') || '', aria: el.getAttribute('aria-label') || '', placeholder: el.getAttribute('placeholder') || '' })")
                comb = f"{f_info.get('name', '')} {f_info.get('id', '')} {f_info.get('auto', '')} {f_info.get('aria', '')} {f_info.get('placeholder', '')}"
                m_el, r_el = is_payment_field(comb, on_pay)
                if m_el:
                    return _err(action, "payment_blocked", page, message=f"Entering details into payment field '{r_el}' is blocked by payment guardrails.", matched_rule=r_el)
            except Exception:
                pass
            try:
                res = _smart_fill_element(page, loc, val, timeout=4000)
                return _ok(action, page, selector=sel, detail=res)
            except Exception as e:
                return _err(action, f"Type failed on {sel!r}: {e}", page)
        if action == "press":
            val, sel = args.get("value") or args.get("key"), args.get("selector")
            if not val: return _err(action, "value (key) required", page)
            if str(val).lower() in ("enter", "return"):
                on_pay, _ = is_payment_url(page.url)
                if sel:
                    m_cta, r_cta = is_payment_cta(sel)
                    m_fld, r_fld = is_payment_field(sel, on_pay)
                    if m_cta or m_fld:
                        return _err(action, "payment_blocked", page, message="Pressing Enter on payment controls is blocked by payment guardrails.", matched_rule=r_cta or r_fld)
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
            m_url, r_url = is_payment_url(url)
            if m_url:
                return _err(action, "payment_blocked", page, message=f"Navigation to payment/checkout URL ({r_url}) is blocked by safety guardrails. Please complete payments manually in your browser.", matched_rule=r_url)
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
            js_script = r"""(frameMeta) => {
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
                
                return elements.map(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const isHidden = rect.width <= 0 || rect.height <= 0 || style.visibility === 'hidden' || style.opacity === '0' || style.display === 'none';
                    const isDisabled = el.disabled === true || el.getAttribute('aria-disabled') === 'true';
                    const area = Math.round(rect.width * rect.height);

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
                    
                    text = text.replace(/\s+/g, ' ').slice(0, 100);
                    
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
                    
                    let rankTier = 4;
                    if (testId) rankTier = 1;
                    else if (role !== 'generic' && text) rankTier = 2;
                    else if (!isHidden && !isDisabled) rankTier = 3;

                    return {
                        role: role,
                        name: text,
                        tag: tag,
                        testid: testId,
                        placeholder: placeholder,
                        suggested_locator: suggested,
                        selector: suggested,
                        disabled: isDisabled,
                        hidden: isHidden,
                        area: area,
                        rank_tier: rankTier,
                        frame_name: (frameMeta && frameMeta.name) || "main",
                        frame_url: (frameMeta && frameMeta.url) || ""
                    };
                }).filter(x => !x.hidden && (x.name.length > 0 || ['input', 'textarea', 'select'].includes(x.tag)));
            }"""

            # Walk main frame and child frames (capped at 10 frames)
            frames_to_walk = []
            if hasattr(page, "main_frame") and page.main_frame:
                frames_to_walk.append(page.main_frame)
            if hasattr(page, "frames"):
                for f in page.frames:
                    if f not in frames_to_walk and len(frames_to_walk) < 10:
                        frames_to_walk.append(f)
            if not frames_to_walk:
                frames_to_walk = [page]

            for frame in frames_to_walk:
                try:
                    f_name = getattr(frame, "name", "") or "main"
                    f_url = getattr(frame, "url", "") or ""
                    frame_meta = {"name": f_name, "url": f_url}
                    frame_links = frame.evaluate(js_script, frame_meta)
                    if frame_links:
                        all_links.extend(frame_links)
                except Exception:
                    continue
            
            # Rank elements: rank_tier ascending, then area ascending (smaller specific controls prioritized)
            all_links.sort(key=lambda x: (x.get("rank_tier", 4), x.get("area", 9999999)))

            # Deduplicate while preserving rank order
            seen_selectors = set()
            unique_links = []
            for link in all_links:
                sel_key = (link.get("frame_name", ""), link.get("selector", ""))
                if sel_key not in seen_selectors:
                    seen_selectors.add(sel_key)
                    unique_links.append(link)
            
            # Generate 16-char content signature hash for loop detection
            dom_signature = build_dom_signature(page.url, unique_links)
            global _last_observed_url, _last_observed_signature
            _last_observed_url = page.url
            _last_observed_signature = dom_signature

            return _ok(action, page, elements=unique_links[:100], count=len(unique_links[:100]), signature=dom_signature)

        if action == "upload":
            sel, val = args.get("selector"), args.get("value")
            if not val: return _err(action, "value (file path) required", page)
            on_pay, r_url = is_payment_url(page.url)
            if on_pay:
                return _err(action, "payment_blocked", page, message=f"File upload on payment and checkout pages ({r_url}) is blocked by safety guardrails.", matched_rule="payment_page_upload")
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
            
            on_pay, _ = is_payment_url(page.url)
            results = {}
            skipped_payment_fields = []
            for sel, text_val in val.items():
                m_fld, r_fld = is_payment_field(str(sel), on_pay)
                if m_fld or is_pan_number(str(text_val)):
                    skipped_payment_fields.append({"field": sel, "rule": r_fld or "pan_number"})
                    continue
                try:
                    f_loc = _resolve_form_field(page, sel)
                    try:
                        f_info = f_loc.evaluate("el => ({ name: el.getAttribute('name') || '', id: el.id || '', auto: el.getAttribute('autocomplete') || '', aria: el.getAttribute('aria-label') || '' })")
                        comb = f"{f_info.get('name', '')} {f_info.get('id', '')} {f_info.get('auto', '')} {f_info.get('aria', '')}"
                        m_el, r_el = is_payment_field(comb, on_pay)
                        if m_el:
                            skipped_payment_fields.append({"field": sel, "rule": r_el})
                            continue
                    except Exception:
                        pass
                except Exception:
                    pass
                try:
                    loc = _resolve_form_field(page, sel)
                    res = _smart_fill_element(page, loc, text_val, timeout=4000)
                    results[sel] = res
                except Exception as e:
                    results[sel] = {"status": "failed", "error": str(e)}

            # Optional submit
            submitted = False
            submit_arg = args.get("submit") or args.get("submit_form")
            if submit_arg:
                sub_sel = args.get("submit_selector") or "button[type=submit], input[type=submit], button:has-text('Submit'), button:has-text('Save'), button:has-text('Send'), button:has-text('Log in'), button:has-text('Sign in')"
                try:
                    sub_btn = page.locator(sub_sel).first
                    if sub_btn.count() > 0:
                        sub_btn.click(timeout=4000)
                        submitted = True
                    else:
                        page.keyboard.press("Enter")
                        submitted = True
                except Exception:
                    pass

            return _ok(action, page, results=results, submitted=submitted)

        if action in ("enter_table_data", "fill_table", "spreadsheet_entry"):
            """Bulk or sequential tabular data entry for Google Sheets, Excel Online, Airtable, Notion tables, and web datagrids."""
            import json
            raw_data = args.get("value") or args.get("data")
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except Exception:
                    lines = [ln.strip() for ln in raw_data.strip().splitlines() if ln.strip()]
                    parsed = []
                    for ln in lines:
                        delimiter = "\t" if "\t" in ln else ","
                        parsed.append([cell.strip() for cell in ln.split(delimiter)])
                    raw_data = parsed

            # Normalize to 2D list of strings: list[list[str]]
            table_2d = []
            if isinstance(raw_data, list):
                if len(raw_data) > 0 and isinstance(raw_data[0], dict):
                    headers = list(raw_data[0].keys())
                    include_headers = args.get("include_headers", True)
                    if include_headers:
                        table_2d.append(headers)
                    for row_dict in raw_data:
                        table_2d.append([str(row_dict.get(h, "")) for h in headers])
                elif len(raw_data) > 0 and isinstance(raw_data[0], list):
                    table_2d = [[str(cell) for cell in row] for row in raw_data]
                else:
                    table_2d = [[str(cell)] for cell in raw_data]

            if not table_2d:
                return _err(action, "data/value must be a non-empty 2D array, list of dicts, or CSV/TSV string", page)

            sel = args.get("selector")
            mode = (args.get("mode") or "auto").lower()

            if sel:
                loc = _get_loc(page, sel)
                try:
                    loc.scroll_into_view_if_needed(timeout=2000)
                    loc.click(timeout=3000)
                except Exception:
                    pass

            row_count = len(table_2d)
            col_count = max(len(r) for r in table_2d) if table_2d else 0

            u_lower = (page.url or "").lower()
            is_spreadsheet = any(host in u_lower for host in ("docs.google.com/spreadsheets", "office.com", "office.live.com", "airtable.com", "notion.so"))
            use_clipboard = (mode == "clipboard") or (mode == "auto" and (is_spreadsheet or not sel))

            method_used = "keyboard"
            if use_clipboard:
                tsv_text = "\n".join("\t".join(str(cell) for cell in row) for row in table_2d)
                try:
                    if hasattr(page, "context") and page.context:
                        try: page.context.grant_permissions(["clipboard-read", "clipboard-write"])
                        except Exception: pass
                    page.evaluate("(text) => navigator.clipboard.writeText(text)", tsv_text)
                    time.sleep(0.1)
                    page.keyboard.press("Control+V")
                    method_used = "clipboard_tsv_paste"
                    return _ok(action, page, rows=row_count, cols=col_count, method=method_used)
                except Exception:
                    method_used = "keyboard"

            # Sequential keyboard navigation: Type cell -> Tab -> next cell -> Enter -> next row
            delay_ms = int(args.get("delay_ms") or 15)
            for r_idx, row in enumerate(table_2d):
                for c_idx, cell_val in enumerate(row):
                    s_cell = str(cell_val)
                    if s_cell:
                        page.keyboard.type(s_cell, delay=delay_ms)
                    if c_idx < len(row) - 1:
                        page.keyboard.press("Tab")
                        time.sleep(0.05)
                if r_idx < len(table_2d) - 1:
                    page.keyboard.press("Enter")
                    time.sleep(0.08)

            return _ok(action, page, rows=row_count, cols=col_count, method=method_used)

        if action in ("extract_table", "scrape_table"):
            """Extract structured tabular data from HTML table, [role=table], [role=grid], or datagrid into JSON, matrix, and Markdown."""
            sel = args.get("selector") or "table, [role=table], [role=grid]"
            script = """(selector) => {
                const root = document.querySelector(selector) || document.querySelector('table') || document.querySelector('[role=table], [role=grid]');
                if (!root) return null;
                
                let headers = [];
                const ths = root.querySelectorAll('thead th, [role=columnheader], tr:first-child th');
                if (ths.length > 0) {
                    headers = Array.from(ths).map(th => th.innerText.trim());
                }
                
                let rows = [];
                const trs = root.querySelectorAll('tbody tr, [role=row]');
                const targetTrs = trs.length > 0 ? trs : root.querySelectorAll('tr');
                
                for (let i = 0; i < targetTrs.length; i++) {
                    const tr = targetTrs[i];
                    if (ths.length > 0 && i === 0 && tr.querySelector('th')) continue;
                    const cells = tr.querySelectorAll('td, th, [role=gridcell], [role=cell]');
                    if (cells.length > 0) {
                        rows.push(Array.from(cells).map(c => c.innerText.trim()));
                    }
                }
                
                if (headers.length === 0 && rows.length > 0) {
                    const maxCols = Math.max(...rows.map(r => r.length));
                    headers = Array.from({length: maxCols}, (_, i) => `Col_${i + 1}`);
                }
                
                return { headers, rows };
            }"""
            res = page.evaluate(script, sel)
            if not res:
                return _err(action, f"No table found matching {sel!r}", page)
                
            headers = res.get("headers", [])
            matrix = res.get("rows", [])
            
            dict_data = []
            for row in matrix:
                row_dict = {}
                for idx, cell in enumerate(row):
                    h_name = headers[idx] if idx < len(headers) else f"Col_{idx + 1}"
                    row_dict[h_name] = cell
                dict_data.append(row_dict)
                
            md_lines = []
            if headers:
                md_lines.append("| " + " | ".join(headers) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for row in matrix[:50]:
                padded = row + [""] * (len(headers) - len(row))
                md_lines.append("| " + " | ".join(padded[:len(headers)]) + " |")
            md_table = "\n".join(md_lines)
            
            return _ok(
                action, page,
                headers=headers,
                row_count=len(matrix),
                col_count=len(headers),
                data=dict_data[:100],
                matrix=matrix[:100],
                markdown=md_table
            )

        if action in ("select_cell", "focus_cell"):
            """Select or focus a specific spreadsheet/grid cell by coordinates (e.g. 'B3') or row/col index."""
            val = (args.get("value") or "").strip()
            sel = args.get("selector")
            u_lower = (page.url or "").lower()
            
            if "docs.google.com/spreadsheets" in u_lower and val:
                try:
                    name_box = page.locator("#t-name-box, input[aria-label='Name box']").first
                    if name_box.count() > 0:
                        name_box.click(timeout=2000)
                        name_box.fill(val)
                        page.keyboard.press("Enter")
                        return _ok(action, page, cell=val, method="name_box")
                except Exception:
                    pass
            
            if sel:
                loc = _get_loc(page, sel)
                loc.scroll_into_view_if_needed(timeout=2000)
                loc.click(timeout=3000)
                return _ok(action, page, selector=sel)
                
            return _ok(action, page, cell=val)

        if action == "select_option":
            sel = args.get("selector")
            val = args.get("value")
            label = args.get("label")
            idx = args.get("index")
            if not sel: return _err(action, "selector required", page)
            loc = _resolve_form_field(page, sel)
            try:
                kwargs = {}
                if label is not None: kwargs["label"] = str(label)
                elif val is not None: kwargs["value"] = str(val)
                elif idx is not None: kwargs["index"] = int(idx)
                else: return _err(action, "value, label, or index required", page)
                
                loc.wait_for(state="visible", timeout=4000)
                loc.scroll_into_view_if_needed(timeout=2000)
                loc.select_option(**kwargs)
                return _ok(action, page, selector=sel, selected=kwargs)
            except Exception as e:
                return _err(action, f"select_option failed on {sel!r}: {e}", page)

        if action in ("scrape_structured", "structured_scrape") or (action == "scrape" and args.get("mode") == "structured"):
            title = page.title() if callable(page.title) else (page.title or "")
            u = page.url or ""
            meta_desc = ""
            try:
                meta_desc = page.evaluate("() => { const el = document.querySelector('meta[name=\"description\"], meta[property=\"og:description\"]'); return el ? (el.getAttribute('content') || '').trim() : ''; }") or ""
            except Exception: pass
            main_text = ""
            try:
                main_text = page.evaluate("() => { const article = document.querySelector('article, main, [role=main], #content, .content'); const root = article || document.body; return (root ? (root.innerText || '') : '').replace(/\\s+/g, ' ').trim().slice(0, 2000); }") or ""
            except Exception: pass
            tables = []
            try:
                tables = page.evaluate("""() => {
                    const results = [];
                    const tbls = document.querySelectorAll('table, [role=table]');
                    for (let t = 0; t < Math.min(tbls.length, 3); t++) {
                        const tbl = tbls[t];
                        let headers = Array.from(tbl.querySelectorAll('thead th, tr:first-child th')).map(th => th.innerText.trim());
                        const rows = [];
                        const trs = tbl.querySelectorAll('tbody tr, tr');
                        for (let r = 0; r < Math.min(trs.length, 30); r++) {
                            const tr = trs[r];
                            if (headers.length > 0 && r === 0 && tr.querySelector('th')) continue;
                            const cells = Array.from(tr.querySelectorAll('td, th')).map(c => c.innerText.trim());
                            if (cells.length > 0) {
                                if (headers.length === 0) headers = cells.map((_, i) => `Col_${i + 1}`);
                                const rowDict = {};
                                cells.forEach((c, idx) => {
                                    const h = headers[idx] || `Col_${idx + 1}`;
                                    rowDict[h] = c;
                                });
                                rows.push(rowDict);
                            }
                        }
                        if (rows.length > 0) results.push({ index: t, headers: headers, rows: rows });
                    }
                    return results;
                }""") or []
            except Exception: pass
            price_displays = []
            try:
                price_displays = page.evaluate("""() => {
                    const text = (document.body ? document.body.innerText : '') || '';
                    const matches = text.match(/(?:\\$|€|£|¥|₹|USD|EUR|GBP|CAD|AUD)\\s*\\d+(?:[.,]\\d{2})?/gi) || [];
                    return Array.from(new Set(matches)).slice(0, 10);
                }""") or []
            except Exception: pass
            return _ok(
                action, page,
                title=title,
                url=u,
                meta_description=meta_desc,
                main_text=main_text,
                tables=tables,
                price_display=price_displays,
                notice="READ ONLY — display text only, not checkout. Never auto-click buy."
            )

        if action in ("wait_download", "download"):
            sel = args.get("selector")
            down_timeout = int(args.get("timeout_ms") or args.get("wait_time") or 30000)
            downloads_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Voila", "downloads")
            os.makedirs(downloads_dir, exist_ok=True)
            try:
                with page.expect_download(timeout=down_timeout) as download_info:
                    if sel:
                        m_cta, r_cta = is_payment_cta(sel)
                        if m_cta:
                            return _err(action, "payment_blocked", page, message=f"Download trigger matches payment CTA '{r_cta}'.", matched_rule=r_cta)
                        loc = _get_loc(page, sel)
                        loc.scroll_into_view_if_needed(timeout=2000)
                        loc.click(timeout=5000)
                    elif args.get("url"):
                        dl_url = args.get("url")
                        m_url, r_url = is_payment_url(dl_url)
                        if m_url:
                            return _err(action, "payment_blocked", page, message=f"Download URL matches payment destination '{r_url}'.", matched_rule=r_url)
                        page.goto(dl_url, timeout=down_timeout)
                    else:
                        return _err(action, "selector (to click) or url (to download) required", page)
                download = download_info.value
                suggested = download.suggested_filename
                dest_path = os.path.join(downloads_dir, suggested)
                download.save_as(dest_path)
                file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                return _ok(action, page, path=dest_path, size=file_size, suggested_filename=suggested)
            except Exception as e:
                return _err(action, f"Download failed or timed out: {e}", page)

        if action == "research_extract":
            url = (args.get("url") or "").strip()
            if not url: return _err(action, "url required", page)
            m_url, r_url = is_payment_url(url)
            if m_url:
                return _err(action, "payment_blocked", page, message=f"Navigation to payment/checkout URL ({r_url}) is blocked by safety guardrails.", matched_rule=r_url)
            if not url.startswith("http"): url = "https://" + url
            should_close = args.get("close", True) in (True, "true", "1", 1)
            ctx = page.context if hasattr(page, "context") and page.context else None
            research_page = ctx.new_page() if ctx else page
            try:
                research_page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(0.2)
                title = research_page.title() if callable(research_page.title) else (research_page.title or "")
                meta_desc = ""
                try:
                    meta_desc = research_page.evaluate("() => { const el = document.querySelector('meta[name=\"description\"], meta[property=\"og:description\"]'); return el ? (el.getAttribute('content') || '').trim() : ''; }") or ""
                except Exception: pass
                main_text = ""
                try:
                    main_text = research_page.evaluate("() => { const article = document.querySelector('article, main, [role=main], #content, .content'); const root = article || document.body; return (root ? (root.innerText || '') : '').replace(/\\s+/g, ' ').trim().slice(0, 2000); }") or ""
                except Exception: pass
                price_displays = []
                try:
                    price_displays = research_page.evaluate("() => { const text = (document.body ? document.body.innerText : '') || ''; const matches = text.match(/(?:\\$|€|£|¥|₹|USD|EUR|GBP|CAD|AUD)\\s*\\d+(?:[.,]\\d{2})?/gi) || []; return Array.from(new Set(matches)).slice(0, 10); }") or []
                except Exception: pass
                result_data = {
                    "title": title,
                    "url": url,
                    "meta_description": meta_desc,
                    "main_text": main_text,
                    "price_display": price_displays,
                }
                return _ok(action, page, research=result_data, closed=should_close)
            finally:
                if should_close and research_page != page:
                    try: research_page.close()
                    except Exception: pass

        if action in ("submit_form", "submit"):
            """Submit the active form or click the primary submit button."""
            sub_sel = args.get("selector") or "button[type=submit], input[type=submit], button:has-text('Submit'), button:has-text('Save'), button:has-text('Send'), button:has-text('Log in'), button:has-text('Sign in')"
            try:
                btn = page.locator(sub_sel).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=4000)
                    return _ok(action, page, method="submit_button_click", selector=sub_sel)
                else:
                    page.keyboard.press("Enter")
                    return _ok(action, page, method="enter_key")
            except Exception as e:
                return _err(action, f"Submit failed: {e}", page)
        if action == "eval":
            expr = args.get("value") or args.get("expression")
            if not expr: return _err(action, "value required", page)
            if os.environ.get("VOILA_ALLOW_BROWSER_EVAL", "1").lower() in ("0", "false", "no"):
                return _err(action, "eval_disabled", page, message="Browser script evaluation is disabled by VOILA_ALLOW_BROWSER_EVAL=0")
            m_ev, r_ev = is_payment_eval(expr)
            if m_ev:
                return _err(action, "payment_blocked", page, message=f"Script modification of payment fields is blocked by payment guardrails ({r_ev}).", matched_rule=r_ev)
            try:
                res = page.evaluate(expr)
                return _ok(action, page, result=res)
            except Exception as e:
                return _err(action, f"Eval failed: {e}", page)
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
        print(json.dumps(mask_sensitive(r), default=str))
        if isinstance(r, dict) and r.get("ok") is False: sys.exit(2)
    except Exception as e:
        err_msg = str(e)
        err_code = "cdp_unavailable" if "cdp_unavailable" in err_msg or "failed to start" in err_msg else "browser_error"
        print(json.dumps({"ok": False, "error": err_code, "message": err_msg, "action": a.action}))
        sys.exit(1)

if __name__ == "__main__":
    main()
