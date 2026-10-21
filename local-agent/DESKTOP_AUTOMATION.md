# Desktop Automation Tool — Voila Local Agent

Controls the native Windows UI via the UIA (UI Automation) accessibility tree.  
No screenshots. No screen recording. Pure structural UIA tree traversal + humanized cursor motion.

---

## Quick Start

```bash
# Snapshot the foreground window
python desktop_tools.py --action snapshot

# Find all buttons
python desktop_tools.py --action find --selector "role=Button"

# Click element e3 (cursor moves humanized)
python desktop_tools.py --action click_ref --ref e3

# Type into element e5
python desktop_tools.py --action set_value --ref e5 --value "Hello World"
```

---

## Dependencies

| Package | Version | Install |
|---|---|---|
| `uiautomation` | ≥2.0 | `pip install uiautomation` |
| `pyautogui` | any | pre-installed |
| `ctypes` | stdlib | built-in |

---

## Architecture

```
LLM / Agent
    │  action + ref (no coordinates)
    ▼
desktop_tools.py         ← UIA tree walker, ref registry, action dispatcher
    │  cx,cy from bounds
    ▼
cursor_motion.py         ← THE ONLY pointer motion module
    │  SetCursorPos, mouse_event (Win32)
    ▼
Windows UIA / Desktop
```

---

## Ref Lifecycle

1. `snapshot` or `find` **clears and rebuilds** the ref store.
2. Refs (`e1`, `e2`, …) are **valid until the next snapshot/find** or until the UI changes (navigation, dialog open/close).
3. If a ref's underlying control is gone, the tool returns `error: ref_stale`.
4. **Always re-snapshot after major UI transitions.**

---

## cursor_motion Contract

- `go(x, y, click=None, drag_to=None, duration_ms=None)` — single entry point.  
- Minimum-jerk speed profile + cubic Bézier curve + Gaussian pixel noise.  
- Duration auto-scaled by distance: clamp `[180, 900]` ms.  
- Pre-click hover `30–120 ms`; mouse-down/up gap `30–80 ms`.  
- Returns telemetry `{x, y, moved, duration_ms, distance_px}`.  
- Set `VOILA_CURSOR_DEBUG=1` for verbose stderr logs.

---

## Tool API

### Parameters

| Param | Type | Description |
|---|---|---|
| `action` | string | Required. One of the actions listed below. |
| `ref` | string | Element ref from last snapshot/find (e.g. `e3`) |
| `selector` | string | Filter like `role=Button;name=Save` or `name=Open` |
| `value` | string | Text to type, keys to send, or drag destination `x,y` |
| `window` | string | Title substring; default = foreground window |
| `depth` | int | Tree depth (default 8, max 15) |
| `timeout_ms` | int | Timeout for operations (default 5000) |

### Actions

| Action | Description |
|---|---|
| `list_windows` | All top-level window titles + PIDs |
| `foreground` | Current foreground window info |
| `snapshot` | Full compact tree with refs and bounds |
| `find` | Filter elements by selector; return matches |
| `move_cursor` | Humanized move only, no click |
| `invoke` | Move cursor → UIA Invoke / click |
| `click_ref` | Move cursor → left click |
| `set_value` | Move cursor → focus → set text (ValuePattern + fallback typing) |
| `type_keys` | Send keys to focused control (optionally focus via ref first) |
| `toggle` | Move cursor → toggle checkbox/switch |
| `focus` | Move cursor → set keyboard focus |
| `select` | Move cursor → select item (SelectionItem pattern) |
| `drag_ref` | Humanized drag from ref to `x,y` or another ref |

### Response Schema

```json
{
  "ok": true,
  "action": "invoke",
  "method": "invoke",
  "retried": false,
  "target_warning": null,
  "ref_generation": 3,
  "window": { "title": "...", "pid": 0 },
  "elements": [
    {
      "ref": "e1",
      "role": "ButtonControl",
      "name": "OK",
      "automation_id": "btnOK",
      "value": "",
      "states": [],
      "bounds": { "x": 100, "y": 200, "w": 80, "h": 30 }
    }
  ],
  "count": 1,
  "cursor": { "x": 140, "y": 215, "moved": true, "duration_ms": 320, "distance_px": 450 },
  "error": null
}
```

### Hit Targeting & Click Stack Hierarchy

1. **Pattern-First**: Microsoft UIA patterns (`InvokePattern`, `TogglePattern`, `ValuePattern`, `SelectionItemPattern`) are preferred without moving the physical cursor.
2. **Validated Clickable Point**: `GetClickablePoint()` is validated to ensure it lies strictly inside the control's bounding box and within the virtual screen bounds before dispatching.
3. **Small Control Center**: For controls with `w <= 300` and `h <= 100`, the geometric center is targeted safely.
4. **Actionable Child Search**: For large panes/groups (`w > 300` or `h > 100`), the walker locates the smallest actionable child element (Button, Hyperlink, Edit, MenuItem) within the pane to avoid empty clicks.
5. **Center Fallback with Warning**: If no actionable child is identified, center is clicked and `target_warning: "large_pane_center_click_warning"` is returned.

### Win32 Input & Synchronization

- **SendInput API**: Replaces legacy `mouse_event` with absolute virtual desktop normalization (`0..65535` across multi-monitors via `SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`). Falls back to `mouse_event` if SendInput fails.
- **Process DPI Awareness**: Process initialized with Per-Monitor V2 DPI awareness (`SetProcessDpiAwareness(2)`) so UIA coordinates match physical screen metrics.
- **Atomic Mutexes**: Unconditional cross-process Win32 named mutexes (`VoilaGlobalUIAMutex`, `VoilaGlobalMouseMutex`) and `Mouse_Lock` context managers guarantee that mouse teleportation, click down/up, and cursor restoration execute in an atomic critical section without races.
- **Ref Store Freshness**: Each snapshot increments `ref_generation`. Actions verify the element's `GetRuntimeId()`, enabled state, on-screen bounds, and verify that bounds have not drifted by >50px (else fails immediately with `target_moved` instead of a silent missed click).
- **Postcondition Verification**: `toggle` and `set_value` actions inspect resulting UI state and perform one automatic retry if the action failed.

### Error Codes

| Code | Meaning |
|---|---|
| `platform` | Not running on Windows |
| `not_found` | Window or element not found |
| `ref_stale` | Element ref is no longer valid (UI changed or refreshed) |
| `target_moved` | Element shifted position by >50px between snapshot and action |
| `target_disabled` | Control is disabled and cannot be acted upon |
| `target_offscreen` | Control is clipped or completely off-screen |
| `tree_unavailable` | UIA tree cannot be read |
| `unsupported` | Action not available for this control type |
| `invalid_args` | Missing or malformed arguments |

---

## Safety Notes

- Respects all existing Voila approval rules for high-risk actions.
- Never touches Windows system files or system processes.
- Fails closed on missing refs or empty trees.
- The agent process cannot crash from UIA exceptions (all caught at dispatch level).
