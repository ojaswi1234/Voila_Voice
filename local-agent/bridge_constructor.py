"""
bridge_constructor.py - Orchestrator for browser <-> desktop collaboration.
Calls browser_guide.py to get coords, then uses cursor_motion to act.
"""
import sys
import json
import subprocess
import os

if sys.platform != "win32":
    print(json.dumps({"ok": False, "error": "platform_unsupported", "message": "Bridge is Windows-first. Unsupported platform."}))
    sys.exit(0)

def call_guide(action: str, selector: str = "", value: str = "") -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    guide_script = os.path.join(here, "browser_guide.py")
    args = [sys.executable, guide_script, "--action", action]
    if selector:
        args.extend(["--selector", selector])
    if value:
        args.extend(["--value", value])
        
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            return {"ok": False, "error": "guide_failed", "message": res.stderr}
        return json.loads(res.stdout)
    except Exception as e:
        return {"ok": False, "error": "guide_error", "message": str(e)}

def guided_click(selector: str, value: str, verify: bool = True, button: str = "left", min_confidence: float = 0.55) -> dict:
    # 1. Resolve coords
    guide_action = "resolve_selector" if selector else "resolve_text"
    target = selector if selector else value
    
    resolve_res = call_guide(guide_action, selector, value)
    
    if not resolve_res.get("ok"):
        return {"ok": False, "error": "resolve_failed", "detail": resolve_res}
        
    conf = resolve_res.get("confidence", 0.0)
    if conf < min_confidence:
        return {"ok": False, "error": "low_confidence", "confidence": conf, "detail": resolve_res}
        
    # 2. Click using cursor_motion
    import cursor_motion
    px = resolve_res.get("physical_x", resolve_res.get("screen_x"))
    py = resolve_res.get("physical_y", resolve_res.get("screen_y"))
    
    try:
        motion_res = cursor_motion.go(px, py, click=button)
    except Exception as e:
        return {"ok": False, "error": "motion_failed", "message": str(e)}
        
    # 3. Optional Verify
    verify_res = None
    if verify:
        v_action = "verify_selector" if selector else "verify_text"
        verify_res = call_guide(v_action, selector, value)
        
    return {
        "ok": True,
        "action": "guided_click",
        "target": target,
        "resolve": resolve_res,
        "motion": motion_res,
        "verify": verify_res
    }

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["guided_click", "guided_close_popup"])
    parser.add_argument("--selector", type=str, default="")
    parser.add_argument("--value", type=str, default="")
    parser.add_argument("--verify", type=str, default="true")
    parser.add_argument("--button", type=str, default="left")
    
    args = parser.parse_args()
    verify_bool = args.verify.lower() == "true"
    
    if args.action == "guided_click":
        res = guided_click(args.selector, args.value, verify_bool, args.button)
        print(json.dumps(res))
    elif args.action == "guided_close_popup":
        # Heuristic 1: try common close buttons in DOM
        for sel in [".modal-close", ".close-button", "[aria-label='Close']", "button:has-text('Close')"]:
            res = guided_click(sel, "", verify=False, button="left", min_confidence=0.4)
            if res.get("ok"):
                print(json.dumps({"ok": True, "message": f"Closed using {sel}", "detail": res}))
                return
        
        # Heuristic 2: fallback to desktop OS-level dialog buttons
        import desktop_core
        for btn_name in ["Close", "Cancel", "X", "Dismiss", "No thanks"]:
            find_res = desktop_core.act_find(None, 10, "", btn_name)
            if find_res.get("ok") and find_res.get("elements"):
                # Grab the first match that is a button-like element
                for el in find_res["elements"]:
                    if "button" in el.get("control_type", "").lower() or btn_name in el.get("name", ""):
                        # Click it using desktop_core router so it passes Python policy gates
                        import argparse
                        args_dispatch = argparse.Namespace(
                            action="click_ref",
                            ref=el["ref"],
                            selector="",
                            value="",
                            window=None,
                            depth=1,
                            timeout=0,
                            button="left",
                            monitor=0
                        )
                        click_res = desktop_core.dispatch(args_dispatch)
                        if click_res.get("ok"):
                            print(json.dumps({"ok": True, "message": f"Closed OS dialog using button '{btn_name}'", "detail": click_res}))
                            return
        
        print(json.dumps({"ok": False, "error": "no_popup_found"}))

if __name__ == "__main__":
    main()
