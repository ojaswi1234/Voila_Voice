"""desktop_core.py — Real UIA + cursor logic for desktop_automation.

Imported ONLY by desktop_bridge.py which runs in the user's Session 1.
desktop_tools.py (the proxy) never imports this.
"""
import sys, os, json, argparse
from typing import Any

# ─── Platform guard ────────────────────────────────────────────────────────────
if sys.platform != "win32":
    def dispatch(args):
        return {"ok": False, "error": "platform", "message": "Windows only"}
else:
    import uiautomation as auto
    import cursor_motion   # THE ONLY motion module

    # ─── Ref registry ──────────────────────────────────────────────────────────
    _ref_store: dict[str, dict] = {}
    _ref_counter = 0

    def _new_ref(ctrl, meta: dict) -> str:
        global _ref_counter
        _ref_counter += 1
        ref = f"e{_ref_counter}"
        _ref_store[ref] = {"ctrl": ctrl, "meta": meta}
        return ref

    def _resolve_ref(ref: str):
        if ref not in _ref_store:
            return None, "ref_stale"
        ctrl = _ref_store[ref]["ctrl"]
        try:
            _ = ctrl.GetRuntimeId()
            return ctrl, None
        except Exception:
            return None, "ref_stale"

    # ─── Tree walker ───────────────────────────────────────────────────────────
    MAX_NODES = 300

    def _ctrl_meta(ctrl) -> dict:
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

    def _walk(ctrl, depth: int, max_depth: int, nodes: list, count: list):
        if count[0] >= MAX_NODES or depth > max_depth or not ctrl:
            return
        meta = _ctrl_meta(ctrl)
        b = meta["bounds"]
        if b["w"] > 0 or b["h"] > 0 or meta["name"]:
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

    # ─── Window helpers ────────────────────────────────────────────────────────
    def _find_window(title_hint):
        if not title_hint:
            fg = auto.GetForegroundControl()
            return fg if fg else auto.GetRootControl()
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
        return auto.GetRootControl()

    def _window_info(wnd) -> dict:
        try:
            pid = wnd.ProcessId
        except Exception:
            pid = 0
        try:
            title = wnd.Name or ""
        except Exception:
            title = ""
        return {"title": title, "pid": pid}

    # ─── Response builders ─────────────────────────────────────────────────────
    def _ok(action: str, wnd=None, **kwargs) -> dict:
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

    def _center(bounds: dict) -> tuple:
        return bounds["x"] + bounds["w"] // 2, bounds["y"] + bounds["h"] // 2

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
            vl = v.lower()
            if k == "role"          and vl not in meta["role"].lower():          return False
            if k == "name"          and vl not in meta["name"].lower():          return False
            if k == "automation_id" and vl not in meta["automation_id"].lower(): return False
        return True

    # ─── Actions ───────────────────────────────────────────────────────────────
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
        return _ok("foreground", wnd)

    def act_snapshot(window, depth: int) -> dict:
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

    def act_find(window, depth: int, selector: str, value: str) -> dict:
        if not _ref_store:
            snap = act_snapshot(window, depth)
            if not snap["ok"]:
                return snap
        parts = _parse_selector(selector) if selector else {}
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

    def _move_to_ref(ref: str, click=None, drag_to=None, duration_ms=None):
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("move", err, f"ref={ref}"), {}
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        tel = cursor_motion.go(cx, cy, click=click, drag_to=drag_to, duration_ms=duration_ms)
        return None, tel

    def act_move_cursor(ref: str, window) -> dict:
        wnd = _find_window(window)
        err_r, tel = _move_to_ref(ref)
        if err_r:
            return err_r
        r = _ok("move_cursor", wnd)
        r["cursor"] = tel
        return r

    def act_invoke(ref: str, window, timeout_ms: int) -> dict:
        wnd = _find_window(window)
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("invoke", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        tel = cursor_motion.go(cx, cy)
        try:
            ctrl.Click(simulateMove=False)
        except Exception:
            cursor_motion.go(cx, cy, click="left")
        r = _ok("invoke", wnd)
        r["cursor"] = tel
        r["cursor"]["moved"] = True
        return r

    def act_click_ref(ref: str, window, button: str = "left") -> dict:
        wnd = _find_window(window)
        err_r, tel = _move_to_ref(ref, click=button)
        if err_r:
            return err_r
        r = _ok("click_ref", wnd)
        r["cursor"] = tel
        return r

    def act_set_value(ref: str, value: str, window) -> dict:
        wnd = _find_window(window)
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("set_value", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        tel = cursor_motion.go(cx, cy, click="left")
        try:
            ctrl.SetValue(value)
        except Exception:
            try:
                ctrl.SendKeys("^a", waitTime=0.05)
                ctrl.SendKeys(value, waitTime=0)
            except Exception as e:
                return _err("set_value", "unsupported", str(e))
        r = _ok("set_value", wnd)
        r["cursor"] = tel
        return r

    def act_type_keys(keys: str, ref, window) -> dict:
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

    def act_toggle(ref: str, window) -> dict:
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
            pass
        r = _ok("toggle", wnd)
        r["cursor"] = tel
        return r

    def act_focus(ref: str, window) -> dict:
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

    def act_select(ref: str, window) -> dict:
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

    def act_drag_ref(ref: str, value: str, window) -> dict:
        wnd = _find_window(window)
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("drag_ref", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        sx, sy = _center(meta["bounds"])
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

    # ─── Router ────────────────────────────────────────────────────────────────
    def dispatch(args) -> dict:
        action   = args.action
        ref      = args.ref or ""
        selector = args.selector or ""
        value    = args.value or ""
        window   = args.window or None
        depth    = min(max(1, args.depth), 15)
        timeout  = args.timeout

        if action == "list_windows":  return act_list_windows()
        if action == "foreground":    return act_foreground()
        if action == "snapshot":      return act_snapshot(window, depth)
        if action == "find":          return act_find(window, depth, selector, value)
        if action == "move_cursor":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_move_cursor(ref, window)
        if action == "invoke":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_invoke(ref, window, timeout)
        if action == "click_ref":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_click_ref(ref, window)
        if action == "set_value":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_set_value(ref, value, window)
        if action == "type_keys":
            if not value: return _err(action, "invalid_args", "value (keys) required")
            return act_type_keys(value, ref or None, window)
        if action == "toggle":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_toggle(ref, window)
        if action == "focus":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_focus(ref, window)
        if action == "select":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_select(ref, window)
        if action == "drag_ref":
            if not ref or not value: return _err(action, "invalid_args", "ref and value required")
            return act_drag_ref(ref, value, window)
        return _err(action, "unsupported", f"Unknown action: {action!r}")
