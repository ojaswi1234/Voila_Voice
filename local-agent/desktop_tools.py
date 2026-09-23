"""desktop_tools.py — Windows UIA desktop automation tool for Voila.

Uses the uiautomation library (Windows UIA accessibility tree) for perception
and cursor_motion.py exclusively for all pointer movement.

CLI:
    python desktop_tools.py --action <action> [--ref e1] [--selector ...] \
                             [--value ...] [--window ...] [--depth 8] \
                             [--timeout 5000]

Always outputs exactly ONE JSON object to stdout.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os, json, argparse, time, threading
from typing import Any

# ─── Platform guard ────────────────────────────────────────────────────────────
if sys.platform != "win32":
    print(json.dumps({"ok": False, "error": "platform", "message": "desktop_automation requires Windows"}))
    sys.exit(0)

import uiautomation as auto
import cursor_motion  # THE ONLY motion module

# ─── Ref registry ──────────────────────────────────────────────────────────────
# Maps "e1", "e2", … → uiautomation Control objects + metadata snapshot.
# Refs are per-session; stale detection uses RuntimeId comparison.
_ref_store: dict[str, dict] = {}   # ref → {ctrl, meta}
_ref_counter = 0

def _new_ref(ctrl: auto.Control, meta: dict) -> str:
    global _ref_counter
    _ref_counter += 1
    ref = f"e{_ref_counter}"
    _ref_store[ref] = {"ctrl": ctrl, "meta": meta}
    return ref

def _resolve_ref(ref: str) -> tuple[auto.Control | None, str | None]:
    """Return (control, None) or (None, error_code)."""
    if ref not in _ref_store:
        return None, "ref_stale"
    entry = _ref_store[ref]
    ctrl = entry["ctrl"]
    try:
        # Probe liveness via RuntimeId
        _ = ctrl.GetRuntimeId()
        return ctrl, None
    except Exception:
        return None, "ref_stale"

# ─── Tree walker ───────────────────────────────────────────────────────────────
MAX_NODES = 300   # cap total elements per snapshot

INTERACTIVE_ROLES = {
    auto.ControlType.ButtonControl,
    auto.ControlType.EditControl,
    auto.ControlType.TextControl,
    auto.ControlType.CheckBoxControl,
    auto.ControlType.RadioButtonControl,
    auto.ControlType.ComboBoxControl,
    auto.ControlType.ListItemControl,
    auto.ControlType.MenuItemControl,
    auto.ControlType.SliderControl,
    auto.ControlType.TabItemControl,
    auto.ControlType.ToolBarControl,
    auto.ControlType.HyperlinkControl,
    auto.ControlType.TreeItemControl,
    auto.ControlType.DataItemControl,
    auto.ControlType.SplitButtonControl,
    auto.ControlType.SpinnerControl,
}

def _ctrl_meta(ctrl: auto.Control) -> dict:
    """Extract compact metadata from a control."""
    try:
        rect = ctrl.BoundingRectangle
        bounds = {"x": rect.left, "y": rect.top,
                  "w": rect.width(), "h": rect.height()}
    except Exception:
        bounds = {"x": 0, "y": 0, "w": 0, "h": 0}

    states = []
    try:
        if not ctrl.IsEnabled:
            states.append("disabled")
        if ctrl.HasKeyboardFocus:
            states.append("focused")
    except Exception:
        pass
    try:
        if hasattr(ctrl, "Toggle") and ctrl.TogglePattern:
            from uiautomation import ToggleState
            ts = ctrl.CurrentToggleState
            states.append("checked" if ts == ToggleState.On else "unchecked")
    except Exception:
        pass

    value = ""
    try:
        if hasattr(ctrl, "Value"):
            value = ctrl.Value or ""
    except Exception:
        pass

    return {
        "role": ctrl.ControlTypeName,
        "name": ctrl.Name or "",
        "automation_id": ctrl.AutomationId or "",
        "value": value,
        "states": states,
        "bounds": bounds,
    }

def _walk(ctrl: auto.Control, depth: int, max_depth: int, nodes: list, count: list):
    if count[0] >= MAX_NODES or depth > max_depth:
        return
    if not ctrl:
        return

    meta = _ctrl_meta(ctrl)
    b = meta["bounds"]
    # Skip zero-area (invisible) elements unless they have a name
    if b["w"] == 0 and b["h"] == 0 and not meta["name"]:
        pass
    else:
        ref = _new_ref(ctrl, meta)
        node = {"ref": ref}
        node.update(meta)
        nodes.append(node)
        count[0] += 1

    try:
        child = ctrl.GetFirstChildControl()
        while child and count[0] < MAX_NODES:
            _walk(child, depth + 1, max_depth, nodes, count)
            child = child.GetNextSiblingControl()
    except Exception:
        pass

# ─── Window helpers ────────────────────────────────────────────────────────────

def _find_window(title_hint: str | None) -> auto.Control | None:
    if not title_hint:
        fg = auto.GetForegroundControl()
        # Fallback to Desktop root when running in a sandboxed session
        return fg if fg else auto.GetRootControl()
    # Walk all top-level windows looking for a partial title match
    wnd = auto.GetRootControl().GetFirstChildControl()
    while wnd:
        try:
            if title_hint.lower() in (wnd.Name or "").lower():
                return wnd
        except Exception:
            pass
        try:
            wnd = wnd.GetNextSiblingControl()
        except Exception:
            break
    # Fallback to root if no match found
    return auto.GetRootControl()

def _window_info(wnd: auto.Control) -> dict:
    try:
        pid = wnd.ProcessId
    except Exception:
        pid = 0
    try:
        title = wnd.Name or ""
    except Exception:
        title = ""
    return {"title": title, "pid": pid}

# ─── Response builders ─────────────────────────────────────────────────────────

def _ok(action: str, wnd: auto.Control | None = None, **kwargs) -> dict:
    r: dict[str, Any] = {"ok": True, "action": action, "error": None}
    r["window"] = _window_info(wnd) if wnd else {}
    r["elements"] = []
    r["count"] = 0
    r["cursor"] = {"x": 0, "y": 0, "moved": False, "duration_ms": 0, "distance_px": 0}
    r.update(kwargs)
    return r

def _err(action: str, code: str, msg: str = "") -> dict:
    return {"ok": False, "action": action, "error": code,
            "message": msg, "elements": [], "count": 0,
            "window": {}, "cursor": {}}

# ─── Center of bounds ──────────────────────────────────────────────────────────

def _center(bounds: dict) -> tuple[int, int]:
    return bounds["x"] + bounds["w"] // 2, bounds["y"] + bounds["h"] // 2

# ─── Selector parsing ──────────────────────────────────────────────────────────
# Selector format: "role=Button;name=Save" or "name=Open" or "automation_id=btn1"

def _parse_selector(sel: str) -> dict:
    parts = {}
    for seg in sel.split(";"):
        seg = seg.strip()
        if "=" in seg:
            k, v = seg.split("=", 1)
            parts[k.strip().lower()] = v.strip()
    return parts

def _matches_selector(meta: dict, parts: dict) -> bool:
    for k, v in parts.items():
        v_lower = v.lower()
        if k == "role" and v_lower not in meta["role"].lower():
            return False
        if k == "name" and v_lower not in meta["name"].lower():
            return False
        if k == "automation_id" and v_lower not in meta["automation_id"].lower():
            return False
    return True

# ─── Actions ───────────────────────────────────────────────────────────────────

def act_list_windows() -> dict:
    results = []
    try:
        wnd = auto.GetRootControl().GetFirstChildControl()
        while wnd:
            try:
                name = wnd.Name or ""
                pid  = wnd.ProcessId
                if name:
                    results.append({"title": name, "pid": pid})
            except Exception:
                pass
            try:
                wnd = wnd.GetNextSiblingControl()
            except Exception:
                break
    except Exception as e:
        return _err("list_windows", "tree_unavailable", str(e))
    r = _ok("list_windows")
    r["windows"] = results
    r["count"] = len(results)
    return r

def act_foreground() -> dict:
    try:
        wnd = auto.GetForegroundControl()
        if not wnd:
            return _err("foreground", "not_found", "No foreground window")
    except Exception as e:
        return _err("foreground", "tree_unavailable", str(e))
    r = _ok("foreground", wnd)
    return r

def act_snapshot(window: str | None, depth: int) -> dict:
    global _ref_store, _ref_counter
    _ref_store.clear()
    _ref_counter = 0

    wnd = _find_window(window)
    if not wnd:
        return _err("snapshot", "not_found", f"Window not found: {window!r}")

    nodes: list = []
    count = [0]
    try:
        _walk(wnd, 0, depth, nodes, count)
    except Exception as e:
        return _err("snapshot", "tree_unavailable", str(e))

    r = _ok("snapshot", wnd)
    r["elements"] = nodes
    r["count"] = len(nodes)
    return r

def act_find(window: str | None, depth: int, selector: str, value: str) -> dict:
    # Re-use current refs OR take a fresh snapshot
    if not _ref_store:
        snap = act_snapshot(window, depth)
        if not snap["ok"]:
            return snap

    parts = _parse_selector(selector) if selector else {}
    # Also support value as JSON filter override
    if value:
        try:
            parts.update(json.loads(value))
        except Exception:
            if "=" in value:
                parts.update(_parse_selector(value))

    wnd = _find_window(window)
    matches = []
    for ref, entry in list(_ref_store.items()):
        meta = entry["meta"]
        if _matches_selector(meta, parts):
            node = {"ref": ref}
            node.update(meta)
            matches.append(node)

    r = _ok("find", wnd)
    r["elements"] = matches
    r["count"] = len(matches)
    return r

def _move_to_ref(ref: str, click: str | None = None,
                  drag_to: tuple[int,int] | None = None,
                  duration_ms: int | None = None) -> tuple[dict | None, dict]:
    """Resolve ref → bounds → cursor_motion.go. Returns (error_dict|None, telemetry)."""
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("move", err, f"ref={ref}"), {}
    meta = _ref_store[ref]["meta"]
    cx, cy = _center(meta["bounds"])
    tel = cursor_motion.go(cx, cy, click=click, drag_to=drag_to, duration_ms=duration_ms)
    return None, tel

def act_move_cursor(ref: str, window: str | None) -> dict:
    wnd = _find_window(window)
    err_r, tel = _move_to_ref(ref)
    if err_r:
        return err_r
    r = _ok("move_cursor", wnd)
    r["cursor"] = tel
    return r

def act_invoke(ref: str, window: str | None, timeout_ms: int) -> dict:
    wnd = _find_window(window)
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("invoke", err, f"ref={ref}")
    meta = _ref_store[ref]["meta"]

    # Move cursor first
    cx, cy = _center(meta["bounds"])
    tel = cursor_motion.go(cx, cy, click=None)  # arrive first

    # Try UIA InvokePattern, fallback to left click
    invoked = False
    try:
        if ctrl.IsEnabled:
            ctrl.Click(simulateMove=False)
            invoked = True
    except Exception:
        pass
    if not invoked:
        cursor_motion.go(cx, cy, click="left")

    r = _ok("invoke", wnd)
    r["cursor"] = tel
    r["cursor"]["moved"] = True
    return r

def act_click_ref(ref: str, window: str | None, button: str = "left") -> dict:
    wnd = _find_window(window)
    err_r, tel = _move_to_ref(ref, click=button)
    if err_r:
        return err_r
    r = _ok("click_ref", wnd)
    r["cursor"] = tel
    return r

def act_set_value(ref: str, value: str, window: str | None) -> dict:
    wnd = _find_window(window)
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("set_value", err, f"ref={ref}")
    meta = _ref_store[ref]["meta"]
    cx, cy = _center(meta["bounds"])

    # Move cursor to field first (humanized)
    tel = cursor_motion.go(cx, cy, click="left")

    try:
        # Try ValuePattern
        ctrl.SetValue(value)
    except Exception:
        # Fallback: clear and type
        try:
            ctrl.SendKeys("^a", waitTime=0.05)
            ctrl.SendKeys(value, waitTime=0)
        except Exception as e:
            return _err("set_value", "unsupported", str(e))

    r = _ok("set_value", wnd)
    r["cursor"] = tel
    return r

def act_type_keys(keys: str, ref: str | None, window: str | None) -> dict:
    wnd = _find_window(window)
    tel = {"x": 0, "y": 0, "moved": False, "duration_ms": 0, "distance_px": 0}

    if ref:
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("type_keys", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        tel = cursor_motion.go(cx, cy, click="left")
        try:
            ctrl.SendKeys(keys, waitTime=0)
        except Exception:
            auto.SendKeys(keys)
    else:
        auto.SendKeys(keys)

    r = _ok("type_keys", wnd)
    r["cursor"] = tel
    return r

def act_toggle(ref: str, window: str | None) -> dict:
    wnd = _find_window(window)
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("toggle", err, f"ref={ref}")
    meta = _ref_store[ref]["meta"]
    cx, cy = _center(meta["bounds"])
    tel = cursor_motion.go(cx, cy, click="left")

    try:
        ctrl.Toggle()
    except Exception:
        pass  # click already toggled it

    r = _ok("toggle", wnd)
    r["cursor"] = tel
    return r

def act_focus(ref: str, window: str | None) -> dict:
    wnd = _find_window(window)
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("focus", err, f"ref={ref}")
    meta = _ref_store[ref]["meta"]
    cx, cy = _center(meta["bounds"])
    tel = cursor_motion.go(cx, cy, click="left")

    try:
        ctrl.SetFocus()
    except Exception:
        pass

    r = _ok("focus", wnd)
    r["cursor"] = tel
    return r

def act_select(ref: str, window: str | None) -> dict:
    wnd = _find_window(window)
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("select", err, f"ref={ref}")
    meta = _ref_store[ref]["meta"]
    cx, cy = _center(meta["bounds"])
    tel = cursor_motion.go(cx, cy, click="left")

    try:
        ctrl.Select()
    except Exception:
        pass

    r = _ok("select", wnd)
    r["cursor"] = tel
    return r

def act_drag_ref(ref: str, value: str, window: str | None) -> dict:
    wnd = _find_window(window)
    ctrl, err = _resolve_ref(ref)
    if err:
        return _err("drag_ref", err, f"ref={ref}")
    meta = _ref_store[ref]["meta"]
    sx, sy = _center(meta["bounds"])

    # value = "x,y" OR another ref like "e3"
    drag_dest: tuple[int, int] | None = None
    if value and "," in value:
        try:
            parts = value.split(",")
            drag_dest = (int(parts[0].strip()), int(parts[1].strip()))
        except Exception:
            return _err("drag_ref", "invalid_args", f"drag value must be 'x,y': {value!r}")
    elif value and value in _ref_store:
        dest_meta = _ref_store[value]["meta"]
        drag_dest = _center(dest_meta["bounds"])
    else:
        return _err("drag_ref", "invalid_args", f"drag value unresolvable: {value!r}")

    tel = cursor_motion.go(sx, sy, drag_to=drag_dest)

    r = _ok("drag_ref", wnd)
    r["cursor"] = tel
    return r

# ─── Router ────────────────────────────────────────────────────────────────────

def dispatch(args: argparse.Namespace) -> dict:
    action   = args.action
    ref      = args.ref or ""
    selector = args.selector or ""
    value    = args.value or ""
    window   = args.window or None
    depth    = min(max(1, args.depth), 15)
    timeout  = args.timeout

    if action == "list_windows":
        return act_list_windows()
    elif action == "foreground":
        return act_foreground()
    elif action == "snapshot":
        return act_snapshot(window, depth)
    elif action == "find":
        return act_find(window, depth, selector, value)
    elif action == "move_cursor":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_move_cursor(ref, window)
    elif action == "invoke":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_invoke(ref, window, timeout)
    elif action == "click_ref":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_click_ref(ref, window)
    elif action == "set_value":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_set_value(ref, value, window)
    elif action == "type_keys":
        if not value:
            return _err(action, "invalid_args", "value (keys) required")
        return act_type_keys(value, ref or None, window)
    elif action == "toggle":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_toggle(ref, window)
    elif action == "focus":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_focus(ref, window)
    elif action == "select":
        if not ref:
            return _err(action, "invalid_args", "ref required")
        return act_select(ref, window)
    elif action == "drag_ref":
        if not ref or not value:
            return _err(action, "invalid_args", "ref and value (x,y or dest_ref) required")
        return act_drag_ref(ref, value, window)
    else:
        return _err(action, "unsupported", f"Unknown action: {action!r}")

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Voila desktop automation tool (UIA)")
    parser.add_argument("--action",   required=True)
    parser.add_argument("--ref",      default="")
    parser.add_argument("--selector", default="")
    parser.add_argument("--value",    default="")
    parser.add_argument("--window",   default="")
    parser.add_argument("--depth",    type=int, default=8)
    parser.add_argument("--timeout",  type=int, default=5000)
    args = parser.parse_args()

    try:
        result = dispatch(args)
    except Exception as e:
        result = _err(args.action, "platform", str(e))

    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
