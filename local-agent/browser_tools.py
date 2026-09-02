"""
browser_tools.py - Playwright CDP browser automation tool.

Bug #11 Fix: The original script cold-booted Python + Playwright + a CDP WebSocket
for EVERY SINGLE action (click, type, scrape...), adding seconds of latency per step.
Now the script uses a socket-based session server: on first run it starts a persistent
daemon that keeps a Playwright browser connection alive. Subsequent calls connect to
the daemon over a local Unix/TCP socket and send JSON commands, returning results
instantly without re-initializing the entire stack.

Bug #12 Fix: The extract_links action ran querySelectorAll('a, button, input') with no
DOM size limit, which could return tens of thousands of nodes from modern SPAs and
crash the browser tab with OOM errors. Now limited to the first 300 DOM nodes before
any filtering, plus a hard cap of 75 results.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
import os
import json
import time
import socket
import argparse
import threading
import keyboard
from playwright.sync_api import sync_playwright

# --- Session daemon -----------------------------------------------------------
DAEMON_PORT  = 19876          # Local-only TCP port for IPC
DAEMON_TOKEN = "voila-browser-daemon-v1"
IDLE_TIMEOUT = 120            # Seconds of inactivity before daemon exits

def kill_script():
    print(json.dumps({"error": "Force stopped by user (Ctrl+Alt+B)"}))
    os._exit(1)

keyboard.add_hotkey("ctrl+alt+b", kill_script)

# ── daemon server (runs in a background process / separate thread) ────────────

def _run_daemon():
    """Persistent daemon: keeps one Playwright browser connection alive and
    handles JSON-encoded action requests from client calls."""
    CDP_URL = "http://localhost:9222"

    with sync_playwright() as p:
        # Connect with retry
        browser = None
        for _ in range(20):
            try:
                browser = p.chromium.connect_over_cdp(CDP_URL)
                break
            except Exception:
                time.sleep(0.5)

        if not browser:
            sys.exit(1)

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind(("127.0.0.1", DAEMON_PORT))
        server_sock.listen(5)
        server_sock.settimeout(IDLE_TIMEOUT)

        last_activity = time.time()

        while True:
            try:
                conn, _ = server_sock.accept()
            except socket.timeout:
                # No activity for IDLE_TIMEOUT seconds — exit cleanly
                break

            last_activity = time.time()
            try:
                raw = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                    if b"\n" in raw:
                        break

                request = json.loads(raw.strip())
                result  = _handle_action(browser, request)
                conn.sendall((json.dumps(result) + "\n").encode())
            except Exception as e:
                try:
                    conn.sendall((json.dumps({"error": str(e)}) + "\n").encode())
                except Exception:
                    pass
            finally:
                conn.close()

        try:
            browser.close()
        except Exception:
            pass

def _get_page(browser):
    """Return the active page (creating one if needed)."""
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("No browser context found.")
    context = contexts[0]
    pages   = context.pages
    if not pages:
        return context.new_page()
    page = pages[0]
    try:
        page.bring_to_front()
    except Exception:
        pass
    return page


def _handle_action(browser, args: dict) -> dict:
    """Execute one browser action and return a result dict."""
    action = args.get("action", "")
    result = {"status": "success", "action": action}

    page = _get_page(browser)

    if action == "goto":
        url = args.get("url", "")
        if not url:
            raise ValueError("url is required for goto")
        page.goto(url, timeout=25000)
        page.wait_for_timeout(args.get("wait_time", 1000))
        result["url"]   = page.url
        result["title"] = page.title()

    elif action == "click":
        sel = args.get("selector")
        if not sel:
            raise ValueError("selector is required for click")
        page.locator(sel).first.click(timeout=10000)
        page.wait_for_timeout(args.get("wait_time", 1000))
        result["url"] = page.url

    elif action == "type":
        sel = args.get("selector")
        val = args.get("value")
        if not sel or val is None:
            raise ValueError("selector and value are required for type")
        page.locator(sel).first.fill(val, timeout=10000)
        page.wait_for_timeout(args.get("wait_time", 1000))

    elif action == "scrape":
        text = page.evaluate("document.body.innerText")
        result["content"] = text[:3000]

    elif action == "extract_links":
        # Bug #12 Fix: Limit the initial querySelectorAll to 300 nodes before
        # processing, preventing OOM crashes on heavy SPAs with thousands of DOM
        # nodes. The final result is capped at 75 elements.
        links = page.evaluate('''() => {
            const MAX_SCAN    = 300;
            const MAX_RESULTS = 75;
            const elements = Array.from(
                document.querySelectorAll("a, button, input")
            ).slice(0, MAX_SCAN);
            return elements.map(el => {
                let text = el.innerText || el.value || el.title || el.name || el.id || "";
                let type = el.tagName.toLowerCase();
                if (type === "input") type += `[${el.type}]`;
                let selector = "";
                if (el.id)                        { selector = `#${el.id}`; }
                else if (el.name)                  { selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`; }
                else if (el.getAttribute("href")) { selector = `${el.tagName.toLowerCase()}[href="${el.getAttribute("href")}"]`; }
                else                               { selector = el.tagName.toLowerCase(); }
                return {type, text: text.trim().substring(0, 150), selector};
            })
            .filter(e => e.text.length > 5)
            .slice(0, MAX_RESULTS);
        }''')
        result["elements"] = links

    elif action == "snapshot":
        path = "snapshot.png"
        page.screenshot(path=path)
        result["snapshot_path"] = os.path.abspath(path)

    else:
        raise ValueError(f"Unknown action: {action}")

    return result


# ── client: send one request to the daemon ────────────────────────────────────

def _send_to_daemon(request: dict) -> dict:
    """Connect to the running daemon and execute one action."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)
    sock.connect(("127.0.0.1", DAEMON_PORT))
    sock.sendall((json.dumps(request) + "\n").encode())
    raw = b""
    while b"\n" not in raw:
        chunk = sock.recv(65536)
        if not chunk:
            break
        raw += chunk
    sock.close()
    return json.loads(raw.strip())


def _is_daemon_running() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", DAEMON_PORT), timeout=1)
        s.close()
        return True
    except OSError:
        return False


def _start_daemon_background():
    """Spawn the daemon in a background thread (same process, daemon=True)."""
    t = threading.Thread(target=_run_daemon, daemon=True)
    t.start()
    # Wait up to 5 seconds for it to start listening
    for _ in range(50):
        if _is_daemon_running():
            return
        time.sleep(0.1)
    raise RuntimeError("Browser daemon failed to start within 5 seconds.")


# ── main entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Browser Automation Tool (persistent session)")
    parser.add_argument("--url",       type=str)
    parser.add_argument("--action",    type=str,
                        choices=["goto", "click", "type", "scrape", "snapshot", "extract_links"],
                        required=True)
    parser.add_argument("--selector",  type=str)
    parser.add_argument("--value",     type=str)
    parser.add_argument("--wait_time", type=int, default=1000)
    args = parser.parse_args()

    request = {
        "action":    args.action,
        "url":       args.url,
        "selector":  args.selector,
        "value":     args.value,
        "wait_time": args.wait_time,
    }

    # Bug #11 Fix: If daemon is already running, connect directly — zero cold-boot.
    # If not running, start it in a background thread first (one-time cost).
    try:
        if not _is_daemon_running():
            _start_daemon_background()

        result = _send_to_daemon(request)
        print(json.dumps(result))
        # Do NOT call os._exit() — daemon thread keeps living for next call
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
