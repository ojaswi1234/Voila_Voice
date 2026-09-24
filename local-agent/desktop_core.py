"""desktop_core.py — Real UIA + cursor logic for desktop_automation.

Imported ONLY by desktop_bridge.py which runs in the user's Session 1.
desktop_tools.py (the proxy) never imports this.
"""
import sys, os, json, time, ctypes
from typing import Any

# ─── Platform guard ────────────────────────────────────────────────────────────
if sys.platform != "win32":
    def dispatch(args):
        return {"ok": False, "error": "platform", "message": "Windows only"}
else:
    import uiautomation as auto
    import cursor_motion   # THE ONLY motion module

    # Reduce default 10s timeout to 1s so missing elements don't hang the bridge
    auto.SetGlobalSearchTimeout(1.0)

    # ─── Win32 helpers for window management ──────────────────────────────────
    _user32 = ctypes.windll.user32

    def _bring_window_to_foreground(hwnd: int):
        """Reliably bring a window to foreground, handling focus-deny quirks."""
        if not hwnd:
            return
        SW_RESTORE = 9
        # If minimized, restore it first
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)
        # Alt-trick: press alt to allow SetForegroundWindow to work cross-thread
        _user32.keybd_event(0x12, 0, 0, 0)          # VK_ALT down
        _user32.SetForegroundWindow(hwnd)
        _user32.keybd_event(0x12, 0, 2, 0)          # VK_ALT up
        time.sleep(0.08)

    def _hwnd_from_ctrl(ctrl):
        """Get raw HWND from a UIA control."""
        try:
            return ctrl.NativeWindowHandle
        except Exception:
            return 0

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

    # ─── Start Menu / shell special-window detector ─────────────────────────────
    # Win10 Start Menu class names (vary by build)
    _START_MENU_CLASSES_WIN10 = (
        "DV2ControlHost",        # Pre-Win10-1809
        "Windows.UI.Core.CoreWindow",  # UWP-hosted start (1809+)
        "ImmersiveLauncher",     # Edge-case
    )
    # Win11 Start Menu is Windows.UI.Core.CoreWindow owned by StartMenuExperienceHost
    # The UIA ClassName exposed is the same, but name/process differ.

    def _find_start_menu_hwnd() -> int:
        """Return the HWND of the Start Menu if it is currently visible, else 0."""
        u32 = _user32
        # Win10: DV2ControlHost is the classic Start Panel
        hwnd = u32.FindWindowW("DV2ControlHost", None)
        if hwnd and u32.IsWindowVisible(hwnd):
            return hwnd
        # Win10/11: Look for a visible CoreWindow whose title is "Start" (case-insensitive)
        buf = ctypes.create_unicode_buffer(256)
        def _enum_cb(hwnd, _):
            cls_buf = ctypes.create_unicode_buffer(128)
            u32.GetClassNameW(hwnd, cls_buf, 128)
            cls = cls_buf.value
            if "CoreWindow" in cls or "ImmersiveLauncher" in cls:
                u32.GetWindowTextW(hwnd, buf, 256)
                if "start" in buf.value.lower() and u32.IsWindowVisible(hwnd):
                    _start_hwnds.append(hwnd)
            return True
        _start_hwnds: list[int] = []
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
        u32.EnumWindows(EnumWindowsProc(_enum_cb), 0)
        if _start_hwnds:
            return _start_hwnds[0]
        # Win10 1903+ Start menu is inside ApplicationFrameWindow — check foreground
        fg_hwnd = u32.GetForegroundWindow()
        if fg_hwnd:
            cls_buf2 = ctypes.create_unicode_buffer(128)
            u32.GetClassNameW(fg_hwnd, cls_buf2, 128)
            if any(c in cls_buf2.value for c in ("DV2", "CoreWindow", "ImmersiveLauncher")):
                return fg_hwnd
        return 0

    _START_HINTS = frozenset({"start", "start menu", "startmenu", "start_menu"})

    def _is_start_menu_hint(hint: str) -> bool:
        return hint.strip().lower() in _START_HINTS

    def _find_window(title_hint):
        """Find a top-level window.

        Special cases:
        - No hint → foreground window (not desktop root, which has no children)
        - "start" / "start menu" → OS-aware Start Menu detection via Win32 + UIA
        - Regular hint → walk UIA siblings (with foreground fallback if title missing)
        """
        if not title_hint:
            fg = auto.GetForegroundControl()
            return fg if fg else auto.GetRootControl()

        # ── Special: Taskbar ─────────────────────────────────────────────────────
        tb_hint = title_hint.strip().lower()
        if tb_hint in ("taskbar", "tray", "system tray", "system_tray"):
            try:
                tb_ctrl = auto.WindowControl(ClassName="Shell_TrayWnd")
                if tb_ctrl and tb_ctrl.Exists(0, 0):
                    return tb_ctrl
            except Exception:
                pass
            # Fallback Win32
            tb_hwnd = _user32.FindWindowW("Shell_TrayWnd", None)
            if tb_hwnd:
                try:
                    ctrl = auto.ControlFromHandle(tb_hwnd)
                    if ctrl:
                        return ctrl
                except Exception:
                    pass

        # ── Special: Start Menu ──────────────────────────────────────────────────
        if _is_start_menu_hint(title_hint):
            sm_hwnd = _find_start_menu_hwnd()
            if sm_hwnd:
                try:
                    ctrl = auto.ControlFromHandle(sm_hwnd)
                    if ctrl:
                        return ctrl
                except Exception:
                    pass
            # Fallback: foreground is probably the Start Menu when it's open
            fg = auto.GetForegroundControl()
            if fg and "start" in (fg.Name or "").lower():
                return fg
            # Last resort: walk root for any window with "Start" in name
            wnd = auto.GetRootControl().GetFirstChildControl()
            while wnd:
                try:
                    if "start" in (wnd.Name or "").lower():
                        return wnd
                except Exception:
                    pass
                try:
                    wnd = wnd.GetNextSiblingControl()
                except Exception:
                    break
            # Nothing found but Start Menu is open — return foreground anyway
            return auto.GetForegroundControl() or auto.GetRootControl()

        # ── General: walk root children ──────────────────────────────────────────
        wnd = auto.GetRootControl().GetFirstChildControl()
        best = None
        while wnd:
            try:
                wname = (wnd.Name or "").lower()
                if title_hint.lower() in wname:
                    # Prefer exact matches; otherwise keep first match
                    if best is None:
                        best = wnd
                    if wname == title_hint.lower():
                        return wnd   # exact match → done
            except Exception:
                pass
            try:
                wnd = wnd.GetNextSiblingControl()
            except Exception:
                break
        if best:
            return best
        # Fallback: return foreground (better than returning dead desktop root)
        fg = auto.GetForegroundControl()
        return fg if fg else auto.GetRootControl()


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
                    hwnd = _hwnd_from_ctrl(wnd)
                    if name:
                        results.append({"title": name, "pid": pid, "hwnd": hwnd})
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

        is_start = _is_start_menu_hint(window or "")
        is_taskbar = (window or "").strip().lower() in ("taskbar", "tray", "system tray", "system_tray")
        if is_start:
            # Make sure the Start Menu is the active foreground window before walking
            sm_hwnd = _find_start_menu_hwnd()
            if sm_hwnd:
                _bring_window_to_foreground(sm_hwnd)
                time.sleep(0.3)   # let it fully render / rise to top
        elif is_taskbar:
            tb_hwnd = _user32.FindWindowW("Shell_TrayWnd", None)
            if tb_hwnd:
                _bring_window_to_foreground(tb_hwnd)
                time.sleep(0.2)

        wnd = _find_window(window)
        if not wnd:
            return _err("snapshot", "not_found", f"Window not found: {window!r}")
        nodes: list = []
        count = [0]
        try:
            _walk(wnd, 0, depth, nodes, count)
        except Exception as e:
            return _err("snapshot", "tree_unavailable", str(e))

        # If we got no elements (e.g. Start Menu tree invisible from wrong root),
        # try once more from the foreground control
        if len(nodes) == 0 and is_start:
            fg = auto.GetForegroundControl()
            if fg:
                _ref_store.clear()
                _ref_counter = 0
                try:
                    _walk(fg, 0, depth, nodes, count)
                    wnd = fg
                except Exception:
                    pass

        r = _ok("snapshot", wnd)
        r["elements"] = nodes
        r["count"] = len(nodes)
        return r


    def act_find(window, depth: int, selector: str, value: str) -> dict:
        parts = _parse_selector(selector) if selector else {}

        # FIX: If AI mistakenly searches for a Window using selector instead of the window arg
        if not window and parts.get("role", "").lower() in ("window", "windowcontrol"):
            window = parts.get("name", "").replace("*", "")

        snap = act_snapshot(window, depth)
        if not snap["ok"]:
            return snap
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

    def _ensure_window_focused(window):
        """Make sure the target window is in the foreground before acting on it."""
        wnd = _find_window(window)
        if wnd:
            hwnd = _hwnd_from_ctrl(wnd)
            if hwnd:
                _bring_window_to_foreground(hwnd)
        return wnd

    def act_move_cursor(ref: str, window) -> dict:
        wnd = _find_window(window)
        err_r, tel = _move_to_ref(ref)
        if err_r:
            return err_r
        r = _ok("move_cursor", wnd)
        r["cursor"] = tel
        return r

    def act_invoke(ref: str, window, timeout_ms: int) -> dict:
        # FIX: Ensure the window is in foreground before invoking so focus isn't stolen silently
        wnd = _ensure_window_focused(window)
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("invoke", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        
        try:
            # Prefer native UIA Invoke Pattern (doesn't move mouse at all)
            invoke_pat = ctrl.GetInvokePattern()
            if invoke_pat:
                tel = cursor_motion.go(cx, cy)
                invoke_pat.Invoke()
            else:
                raise NotImplementedError()
        except Exception:
            # Fallback to our own safe click that restores physical cursor
            tel = cursor_motion.go(cx, cy, click="left")
            
        # Re-assert focus after invoke to prevent focus loss on certain dialogs
        try:
            ctrl.SetFocus()
        except Exception:
            pass
            
        r = _ok("invoke", wnd)
        r["cursor"] = tel
        r["cursor"]["moved"] = True
        return r

    def act_click_ref(ref: str, window, button: str = "left") -> dict:
        # FIX: Bring window to foreground first to prevent defocus on click
        wnd = _ensure_window_focused(window)
        err_r, tel = _move_to_ref(ref, click=button)
        if err_r:
            return err_r
        r = _ok("click_ref", wnd)
        r["cursor"] = tel
        return r

    def act_right_click(ref: str, window) -> dict:
        """Dedicated right-click action to open context menus."""
        wnd = _ensure_window_focused(window)
        err_r, tel = _move_to_ref(ref, click="right")
        if err_r:
            return err_r
        r = _ok("right_click", wnd)
        r["cursor"] = tel
        return r

    def act_scroll(ref: str, window, value: str) -> dict:
        """Scroll a control. value = 'up'|'down'|'left'|'right' or an integer for wheel delta."""
        wnd = _ensure_window_focused(window)
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("scroll", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        tel = cursor_motion.go(cx, cy)

        WHEEL_DELTA = 120
        VK_NEXT    = 0x22   # Page Down
        VK_PRIOR   = 0x21   # Page Up

        try:
            delta = int(value)
        except (ValueError, TypeError):
            delta = None

        _user32_local = ctypes.windll.user32
        
        # We MUST teleport the physical cursor to the target element to scroll it,
        # otherwise Windows scrolls whatever is under the user's physical mouse!
        pt = ctypes.wintypes.POINT()
        _user32_local.GetCursorPos(ctypes.byref(pt))
        orig_x, orig_y = pt.x, pt.y
        _user32_local.SetCursorPos(int(cx), int(cy))
        time.sleep(0.05)

        try:
            if delta is not None:
                # Positive = scroll up (forward), negative = scroll down
                _user32_local.mouse_event(0x0800, 0, 0, ctypes.c_int(delta * WHEEL_DELTA), 0)
            elif isinstance(value, str) and value.lower() in ("down", ""):
                _user32_local.mouse_event(0x0800, 0, 0, ctypes.c_int(-3 * WHEEL_DELTA), 0)
            elif isinstance(value, str) and value.lower() == "up":
                _user32_local.mouse_event(0x0800, 0, 0, ctypes.c_int(3 * WHEEL_DELTA), 0)
        finally:
            _user32_local.SetCursorPos(int(orig_x), int(orig_y))

        r = _ok("scroll", wnd)
        r["cursor"] = tel
        return r

    def act_set_value(ref: str, value: str, window) -> dict:
        wnd = _ensure_window_focused(window)
        ctrl, err = _resolve_ref(ref)
        if err:
            return _err("set_value", err, f"ref={ref}")
        meta = _ref_store[ref]["meta"]
        cx, cy = _center(meta["bounds"])
        tel = cursor_motion.go(cx, cy, click="left")
        
        def _escape_sendkeys(text: str) -> str:
            # uiautomation uses { } for special keys. To type literal { or }, enclose them in {}.
            res = ""
            for c in text:
                if c in "{}()":
                    res += f"{{{c}}}"
                else:
                    res += c
            return res

        try:
            ctrl.SetValue(value)
        except Exception:
            try:
                ctrl.SendKeys("{Ctrl}a{Delete}", waitTime=0.05)
                ctrl.SendKeys(_escape_sendkeys(value), waitTime=0)
            except Exception as e:
                return _err("set_value", "unsupported", str(e))
        r = _ok("set_value", wnd)
        r["cursor"] = tel
        return r

    def act_type_keys(keys: str, ref, window) -> dict:
        wnd = _ensure_window_focused(window)
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
        wnd = _ensure_window_focused(window)
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
        wnd = _ensure_window_focused(window)
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
        wnd = _ensure_window_focused(window)
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

    # ──────────────────────────────────────────────────────────────────────────
    # NEW: Window / Tab / Desktop management actions
    # ──────────────────────────────────────────────────────────────────────────

    def act_focus_window(window: str) -> dict:
        """Bring a window to the foreground by title hint. Returns updated foreground info."""
        wnd = _find_window(window)
        if not wnd:
            return _err("focus_window", "not_found", f"Window not found: {window!r}")
        hwnd = _hwnd_from_ctrl(wnd)
        _bring_window_to_foreground(hwnd)
        r = _ok("focus_window", wnd)
        r["message"] = f"Focused: {wnd.Name!r}"
        return r

    def act_close_window(window: str) -> dict:
        """Close a window by title hint using Alt+F4."""
        wnd = _find_window(window)
        if not wnd:
            return _err("close_window", "not_found", f"Window not found: {window!r}")
        hwnd = _hwnd_from_ctrl(wnd)
        _bring_window_to_foreground(hwnd)
        time.sleep(0.1)
        # WM_CLOSE = 0x0010
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
        r = _ok("close_window", wnd)
        r["message"] = f"Close sent to: {wnd.Name!r}"
        return r

    def act_switch_tab(direction: str = "next") -> dict:
        """Switch browser / app tabs. direction = 'next'|'prev'|'close'|'new'."""
        _user32_local = ctypes.windll.user32
        # Ctrl+Tab → next, Ctrl+Shift+Tab → prev, Ctrl+W → close, Ctrl+T → new
        VK_CONTROL = 0x11
        VK_SHIFT   = 0x10
        VK_TAB     = 0x09
        VK_W       = 0x57
        VK_T       = 0x54
        KEYEVENTF_KEYUP = 0x0002

        def _keydown(vk):  _user32_local.keybd_event(vk, 0, 0, 0)
        def _keyup(vk):    _user32_local.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        if direction == "next":
            _keydown(VK_CONTROL); _keydown(VK_TAB); time.sleep(0.05); _keyup(VK_TAB); _keyup(VK_CONTROL)
        elif direction == "prev":
            _keydown(VK_CONTROL); _keydown(VK_SHIFT); _keydown(VK_TAB)
            time.sleep(0.05)
            _keyup(VK_TAB); _keyup(VK_SHIFT); _keyup(VK_CONTROL)
        elif direction == "close":
            _keydown(VK_CONTROL); _keydown(VK_W); time.sleep(0.05); _keyup(VK_W); _keyup(VK_CONTROL)
        elif direction == "new":
            _keydown(VK_CONTROL); _keydown(VK_T); time.sleep(0.05); _keyup(VK_T); _keyup(VK_CONTROL)
        else:
            return _err("switch_tab", "invalid_args", f"direction must be next/prev/close/new, got: {direction!r}")

        time.sleep(0.15)  # let the tab switch animate
        r = _ok("switch_tab")
        r["message"] = f"Tab action: {direction}"
        return r

    def act_switch_window(direction: str = "next") -> dict:
        """Cycle through open windows. direction = 'next'|'prev'."""
        _user32_local = ctypes.windll.user32
        VK_MENU    = 0x12   # Alt
        VK_TAB     = 0x09
        VK_SHIFT   = 0x10
        KEYEVENTF_KEYUP = 0x0002

        def _keydown(vk): _user32_local.keybd_event(vk, 0, 0, 0)
        def _keyup(vk):   _user32_local.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

        if direction == "next":
            _keydown(VK_MENU); _keydown(VK_TAB); time.sleep(0.12); _keyup(VK_TAB); _keyup(VK_MENU)
        elif direction == "prev":
            _keydown(VK_MENU); _keydown(VK_SHIFT); _keydown(VK_TAB)
            time.sleep(0.12)
            _keyup(VK_TAB); _keyup(VK_SHIFT); _keyup(VK_MENU)
        else:
            return _err("switch_window", "invalid_args", f"direction must be next/prev, got: {direction!r}")

        time.sleep(0.2)
        r = _ok("switch_window")
        r["message"] = f"Window switch: {direction}"
        return r

    def act_switch_desktop(index: int = -1, direction: str = "next") -> dict:
        """Switch Windows 10/11 virtual desktops.

        Uses SendInput (higher-level than keybd_event, not blocked by session
        restrictions) to send Win+Ctrl+Arrow. Falls back to a PowerShell
        subprocess approach if SendInput is still ineffective.

        If index >= 0 → switch to that specific desktop (0-based).
        Otherwise direction='next'|'prev' moves one desktop.
        """
        import subprocess

        # ── Approach 1: SendInput with KEYEVENTF_EXTENDEDKEY ──────────────────
        # SendInput bypasses the keybd_event session restriction that breaks
        # Win+Ctrl+Arrow when called from a background process on Win10.
        INPUT_KEYBOARD   = 1
        KEYEVENTF_KEYUP  = 0x0002
        KEYEVENTF_EXTENDEDKEY = 0x0001

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk",         ctypes.c_ushort),
                ("wScan",       ctypes.c_ushort),
                ("dwFlags",     ctypes.c_ulong),
                ("time",        ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("_input", INPUT_UNION)]

        def _sinput(vk: int, flags: int = 0) -> INPUT:
            i = INPUT()
            i.type = INPUT_KEYBOARD
            i._input.ki.wVk = vk
            i._input.ki.dwFlags = flags
            return i

        def _send(*inputs):
            arr = (INPUT * len(inputs))(*inputs)
            ctypes.windll.user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

        VK_LWIN    = 0x5B
        VK_CONTROL = 0x11
        VK_LEFT    = 0x25
        VK_RIGHT   = 0x27

        def _one_step_sendinput(right: bool):
            key = VK_RIGHT if right else VK_LEFT
            # Press Win+Ctrl+Arrow, then release all
            _send(
                _sinput(VK_LWIN,    KEYEVENTF_EXTENDEDKEY),
                _sinput(VK_CONTROL, KEYEVENTF_EXTENDEDKEY),
                _sinput(key,        KEYEVENTF_EXTENDEDKEY),
                _sinput(key,        KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP),
                _sinput(VK_CONTROL, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP),
                _sinput(VK_LWIN,    KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP),
            )
            time.sleep(0.4)   # shell needs ~300ms to animate the transition

        # ── Approach 2: PowerShell COM fallback ───────────────────────────────
        # Uses IVirtualDesktopManager via undocumented but stable COM GUIDs.
        # This works even when key injection fails (e.g., some Win10 builds).
        PS_SWITCH_SCRIPT = r"""
$direction = '{dir}'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class VDesktop {
    [DllImport("user32.dll")]
    static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    const int VK_LWIN = 0x5B, VK_CONTROL = 0x11, VK_LEFT = 0x25, VK_RIGHT = 0x27;
    const uint KEYEVENTF_KEYUP = 0x0002, KEYEVENTF_EXTENDEDKEY = 0x0001;
    public static void Switch(bool right) {
        byte key = right ? (byte)VK_RIGHT : (byte)VK_LEFT;
        keybd_event(VK_LWIN, 0, KEYEVENTF_EXTENDEDKEY, UIntPtr.Zero);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_EXTENDEDKEY, UIntPtr.Zero);
        keybd_event(key, 0, KEYEVENTF_EXTENDEDKEY, UIntPtr.Zero);
        System.Threading.Thread.Sleep(80);
        keybd_event(key, 0, KEYEVENTF_EXTENDEDKEY|KEYEVENTF_KEYUP, UIntPtr.Zero);
        keybd_event(VK_CONTROL, 0, KEYEVENTF_EXTENDEDKEY|KEYEVENTF_KEYUP, UIntPtr.Zero);
        keybd_event(VK_LWIN, 0, KEYEVENTF_EXTENDEDKEY|KEYEVENTF_KEYUP, UIntPtr.Zero);
        System.Threading.Thread.Sleep(350);
    }
}
'@
if ($direction -eq 'next') { [VDesktop]::Switch($true) }
else { [VDesktop]::Switch($false) }
"""

        def _ps_step(right: bool):
            script = PS_SWITCH_SCRIPT.replace("{dir}", "next" if right else "prev")
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    timeout=5, capture_output=True
                )
            except Exception:
                pass

        def _one_step(right: bool):
            """Try SendInput first, fall back to PowerShell if needed."""
            try:
                _one_step_sendinput(right)
            except Exception:
                _ps_step(right)

        steps_done = 0
        if index >= 0:
            # Go far left to reach desktop 0, then go right `index` times
            for _ in range(15):
                _one_step(False)
            for _ in range(index):
                _one_step(True)
            steps_done = 15 + index
            r = _ok("switch_desktop")
            r["message"] = f"Switched to desktop index {index} (Win+Ctrl+Arrow, {steps_done} steps)"
        else:
            _one_step(direction == "next")
            r = _ok("switch_desktop")
            r["message"] = f"Switched desktop: {direction}"
        return r


    def act_minimize_window(window: str) -> dict:
        """Minimize a window by title hint."""
        wnd = _find_window(window)
        if not wnd:
            return _err("minimize_window", "not_found", f"Window not found: {window!r}")
        hwnd = _hwnd_from_ctrl(wnd)
        SW_MINIMIZE = 6
        ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
        r = _ok("minimize_window", wnd)
        r["message"] = f"Minimized: {wnd.Name!r}"
        return r

    def act_maximize_window(window: str) -> dict:
        """Maximize a window by title hint."""
        wnd = _find_window(window)
        if not wnd:
            return _err("maximize_window", "not_found", f"Window not found: {window!r}")
        hwnd = _hwnd_from_ctrl(wnd)
        SW_MAXIMIZE = 3
        ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        r = _ok("maximize_window", wnd)
        r["message"] = f"Maximized: {wnd.Name!r}"
        return r

    def act_open_start_menu(depth: int = 6) -> dict:
        """Open the Windows Start Menu and return a snapshot of its contents.

        Works on Win10 (Build 19041+) and Win11.
        Uses VK_LWIN to toggle the Start Menu open, waits for it to become
        the foreground window, then snapshots its UIA tree.
        """
        VK_LWIN = 0x5B
        KEYEVENTF_KEYUP = 0x0002
        u32 = _user32

        # Check if Start Menu is already open (has an HWND)
        already_open = bool(_find_start_menu_hwnd())
        if not already_open:
            u32.keybd_event(VK_LWIN, 0, 0, 0)
            time.sleep(0.05)
            u32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

        # Wait up to 2.5s for the Start Menu HWND to appear and become foreground
        sm_hwnd = 0
        for _ in range(25):
            time.sleep(0.1)
            sm_hwnd = _find_start_menu_hwnd()
            if sm_hwnd:
                break

        if not sm_hwnd:
            # Last attempt: maybe the foreground IS the start menu
            fg = auto.GetForegroundControl()
            if fg and "start" in (fg.Name or "").lower():
                sm_hwnd = _hwnd_from_ctrl(fg)

        if not sm_hwnd:
            return _err("open_start_menu", "not_found",
                        "Start Menu did not open — HWND not found after 2.5s")

        # Ensure it's truly foreground (z-order fix)
        _bring_window_to_foreground(sm_hwnd)
        time.sleep(0.3)

        # Snapshot the Start Menu
        snap = act_snapshot("start", depth)
        snap["action"] = "open_start_menu"
        snap["message"] = f"Start Menu opened and snapshotted — hwnd={sm_hwnd}"
        return snap

    # ─── Router ────────────────────────────────────────────────────────────────
    def dispatch(args) -> dict:
        action   = args.action
        ref      = args.ref or ""
        selector = args.selector or ""
        value    = args.value or ""
        window   = args.window or None
        depth    = min(max(1, args.depth), 15)
        timeout  = args.timeout
        button   = getattr(args, "button", "left") or "left"
        monitor  = getattr(args, "monitor", 0) or 0

        if action == "list_windows":   return act_list_windows()
        if action == "foreground":     return act_foreground()
        if action == "snapshot":       return act_snapshot(window, depth)
        if action == "find":           return act_find(window, depth, selector, value)

        if action == "open_start_menu" or action == "snapshot_start_menu":
            return act_open_start_menu(depth)

        if action == "move_cursor":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_move_cursor(ref, window)

        if action == "invoke":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_invoke(ref, window, timeout)

        if action == "click_ref":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_click_ref(ref, window, button)

        if action == "right_click":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_right_click(ref, window)

        if action == "scroll":
            if not ref: return _err(action, "invalid_args", "ref required")
            return act_scroll(ref, window, value)

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

        # ── New window/tab/desktop actions ──
        if action == "focus_window":
            return act_focus_window(window or value or "")

        if action == "close_window":
            return act_close_window(window or value or "")

        if action == "minimize_window":
            return act_minimize_window(window or value or "")

        if action == "maximize_window":
            return act_maximize_window(window or value or "")

        if action == "switch_tab":
            return act_switch_tab(direction=value or "next")

        if action == "switch_window":
            return act_switch_window(direction=value or "next")

        if action == "switch_desktop":
            # value can be "next"/"prev" or a number like "2"
            try:
                idx = int(value)
                return act_switch_desktop(index=idx)
            except (ValueError, TypeError):
                return act_switch_desktop(direction=value or "next")

        return _err(action, "unsupported", f"Unknown action: {action!r}")

