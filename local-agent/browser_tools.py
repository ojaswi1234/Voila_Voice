import sys
import os
import json
import time
import argparse
import keyboard
from playwright.sync_api import sync_playwright

def kill_script():
    print(json.dumps({"error": "Force stopped by user (Ctrl+Alt+B)"}))
    os._exit(1)

# Register the emergency kill switch
keyboard.add_hotkey('ctrl+alt+b', kill_script)

def main():
    parser = argparse.ArgumentParser(description="Browser Automation Tool")
    parser.add_argument('--url', type=str, help='URL to navigate to (optional for some actions)')
    parser.add_argument('--action', type=str, choices=['goto', 'click', 'type', 'scrape', 'snapshot', 'extract_links'], required=True, help='Action to perform')
    parser.add_argument('--selector', type=str, help='CSS Selector for click/type')
    parser.add_argument('--value', type=str, help='Value for type action')
    parser.add_argument('--wait_time', type=int, default=1000, help='Wait time after action in ms')
    
    args = parser.parse_args()

    CDP_URL = "http://localhost:9222"
    
    try:
        with sync_playwright() as p:
            # Try to connect, retrying for a few seconds in case WMI launch is slow
            browser = None
            for _ in range(15):
                try:
                    browser = p.chromium.connect_over_cdp(CDP_URL)
                    break
                except Exception:
                    time.sleep(0.5)
            
            if not browser:
                print(json.dumps({"error": "Failed to connect to browser on port 9222. Ensure Edge was launched with --remote-debugging-port=9222"}))
                sys.exit(1)

            contexts = browser.contexts
            if not contexts:
                print(json.dumps({"error": "No browser context found."}))
                sys.exit(1)
            
            context = contexts[0]
            pages = context.pages
            if not pages:
                page = context.new_page()
            else:
                page = pages[0]
                try:
                    page.bring_to_front()
                except Exception:
                    pass

            result = {"status": "success", "action": args.action}

            if args.url and args.action == 'goto':
                page.goto(args.url, timeout=25000)
                page.wait_for_timeout(args.wait_time)
                result["url"] = page.url
                result["title"] = page.title()

            elif args.action == 'click':
                if not args.selector:
                    raise ValueError("Selector is required for click action")
                page.locator(args.selector).first.click(timeout=10000)
                page.wait_for_timeout(args.wait_time)
                result["url"] = page.url

            elif args.action == 'type':
                if not args.selector or args.value is None:
                    raise ValueError("Selector and value are required for type action")
                page.locator(args.selector).first.fill(args.value, timeout=10000)
                page.wait_for_timeout(args.wait_time)

            elif args.action == 'scrape':
                text = page.evaluate('document.body.innerText')
                # Limit to 3000 chars for AI context window constraints
                result["content"] = text[:3000]

            elif args.action == 'extract_links':
                # Get interactable elements to help the AI know what to click
                links = page.evaluate('''() => {
                    const elements = Array.from(document.querySelectorAll('a, button, input'));
                    return elements.map(el => {
                        let text = el.innerText || el.value || el.title || el.name || el.id || '';
                        let type = el.tagName.toLowerCase();
                        if (type === 'input') type += `[${el.type}]`;
                        
                        // Need a unique selector for Playwright to click
                        let selector = '';
                        if (el.id) { selector = `#${el.id}`; }
                        else if (el.name) { selector = `${el.tagName.toLowerCase()}[name="${el.name}"]`; }
                        else if (el.getAttribute('href')) { selector = `${el.tagName.toLowerCase()}[href="${el.getAttribute('href')}"]`; }
                        else { selector = el.tagName.toLowerCase(); }
                        
                        return {type: type, text: text.trim().substring(0, 150), selector: selector};
                    }).filter(e => e.text.length > 5 && !e.selector.startsWith('a') || e.selector.includes('href')).slice(0, 100);
                }''')
                result["elements"] = links

            elif args.action == 'snapshot':
                path = "snapshot.png"
                page.screenshot(path=path)
                result["snapshot_path"] = os.path.abspath(path)

            print(json.dumps(result))
            
            # Disconnect safely to keep browser open
            browser.disconnect()
            sys.exit(0)

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
