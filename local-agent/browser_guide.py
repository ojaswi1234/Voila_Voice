"""
browser_guide.py - DOM to Screen Coordinate resolution for Voila Bridge.
Uses Playwright CDP to get viewport bounds and calculates OS screen coordinates.
"""
import sys
import json
import argparse
from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"

def _get_page(p):
    try:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        contexts = browser.contexts
        if not contexts:
            return None, "No contexts"
        pages = contexts[0].pages
        if not pages:
            return None, "No pages"
        return pages[0], None
    except Exception as e:
        return None, str(e)

def resolve_selector(page, selector: str):
    try:
        # Wait a tiny bit if not present, but don't hang
        loc = page.locator(selector).first
        loc.wait_for(state="attached", timeout=2000)
        
        if not loc.is_visible():
            return {"ok": False, "error": "not_visible", "confidence": 0.0}
            
        bbox = loc.bounding_box()
        if not bbox:
            return {"ok": False, "error": "offscreen", "confidence": 0.0}
            
        return _compute_screen_coords(page, bbox, selector)
    except Exception as e:
        return {"ok": False, "error": "not_found", "message": str(e), "confidence": 0.0}

def resolve_text(page, text: str):
    try:
        loc = page.get_by_text(text, exact=False).first
        loc.wait_for(state="attached", timeout=2000)
        
        if not loc.is_visible():
            return {"ok": False, "error": "not_visible", "confidence": 0.0}
            
        bbox = loc.bounding_box()
        if not bbox:
            return {"ok": False, "error": "offscreen", "confidence": 0.0}
            
        return _compute_screen_coords(page, bbox, f"text='{text}'")
    except Exception as e:
        return {"ok": False, "error": "not_found", "message": str(e), "confidence": 0.0}

def _compute_screen_coords(page, bbox, ref_id):
    # Calculate offset using JS
    metrics = page.evaluate("""() => {
        let isMax = (window.outerWidth >= window.screen.availWidth && window.outerHeight >= window.screen.availHeight);
        let borderX = isMax ? 0 : (window.outerWidth - window.innerWidth) / 2;
        let borderYTop = isMax ? (window.outerHeight - window.innerHeight) : (window.outerHeight - window.innerHeight - borderX);
        return {
            wx: window.screenX,
            wy: window.screenY,
            bx: borderX,
            by: borderYTop,
            dpr: window.devicePixelRatio
        };
    }""")
    
    # Coordinates in CSS pixels
    vp_x = bbox["x"] + bbox["width"] / 2
    vp_y = bbox["y"] + bbox["height"] / 2
    
    # OS Screen coordinates
    screen_x = metrics["wx"] + metrics["bx"] + vp_x
    screen_y = metrics["wy"] + metrics["by"] + vp_y
    
    # Ensure physical pixel scaling if OS uses scaled coords (Playwright CDP often returns logical CSS pixels, desktop_tools might expect physical depending on DPI awareness).
    # We will pass DPR so the orchestrator can scale if needed, but often PyAutoGUI operates in logical coords if DPI awareness isn't set, or physical if it is.
    # In Windows, desktop_tools UIA uses physical. We'll return logical and physical.
    
    return {
        "ok": True,
        "action": "resolve",
        "selector": ref_id,
        "screen_x": int(screen_x),
        "screen_y": int(screen_y),
        "physical_x": int(screen_x * metrics["dpr"]),
        "physical_y": int(screen_y * metrics["dpr"]),
        "width": int(bbox["width"]),
        "height": int(bbox["height"]),
        "in_viewport": True,
        "confidence": 0.95 if bbox["width"] > 2 and bbox["height"] > 2 else 0.4,
        "dpr": metrics["dpr"],
        "error": None
    }

def verify_element(page, selector: str, text: str):
    # simple verify: does it exist and is it visible? 
    # For a click, verification usually means the element DISAPPEARED or a NEW element APPEARED.
    # If the user asked to verify, we'll just check if the target state matches.
    # We will return the current state of the DOM for this selector.
    try:
        if selector:
            loc = page.locator(selector).first
        else:
            loc = page.get_by_text(text, exact=False).first
            
        vis = loc.is_visible(timeout=500)
        return {"ok": True, "action": "verify", "visible": vis}
    except Exception:
        return {"ok": True, "action": "verify", "visible": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["resolve_selector", "resolve_text", "verify_selector", "verify_text"])
    parser.add_argument("--selector", type=str, default="")
    parser.add_argument("--value", type=str, default="")
    args = parser.parse_args()

    with sync_playwright() as p:
        page, err = _get_page(p)
        if err or not page:
            print(json.dumps({"ok": False, "error": "cdp_unavailable", "message": err}))
            return

        res = {}
        if args.action == "resolve_selector":
            res = resolve_selector(page, args.selector)
        elif args.action == "resolve_text":
            res = resolve_text(page, args.value)
        elif args.action == "verify_selector":
            res = verify_element(page, args.selector, "")
        elif args.action == "verify_text":
            res = verify_element(page, "", args.value)

        print(json.dumps(res))

if __name__ == "__main__":
    main()
