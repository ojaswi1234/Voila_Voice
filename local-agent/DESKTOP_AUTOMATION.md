# Desktop Automation Tool — Voila Local Agent

Controls the native Windows UI via the UIA (UI Automation) accessibility tree.  
No screenshots. No screen recording. Pure structural UIA tree traversal + pattern-first actions + humanized pointer motion.

---

## Quick Start

```bash
# Snapshot the foreground window (returns ref_generation)
python desktop_tools.py --action snapshot

# Find all buttons
python desktop_tools.py --action find --selector "role=Button"

# Click element e3 using ref_generation for stale cache validation
python desktop_tools.py --action click_ref --ref e3 --ref-generation 1

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
LLM / Agent (Go core / Python agent)
    │  action + ref + ref_generation
    ▼
desktop_tools.py         ← Sandbox proxy (Session 0/exebox → Session 1)
    │  TCP 127.0.0.1:19881 (VOILA_DESKTOP_PORT)
    ▼
desktop_bridge.py        ← Session 1 daemon (Per-Monitor V2 DPI-aware)
    │  desktop_lock (UIA mutex + Mouse critical section)
    ▼
desktop_core.py          ← UIA tree walker, ref registry (TTL 2500ms / generation bypass),
    │                       Pattern short-circuit (Invoke/Toggle/SelectionItem/Value)
    │  (only when pixel fallback needed)
    ▼
cursor_motion.py         ← THE ONLY pointer motion module
    │  SendInput (move+down batching, 0..65535 VIRTUALDESK normalization, mouse_event fallback)
    ▼
Windows UIA / Desktop
```

---

## Ref Lifecycle & Freshness Guarantees

1. `snapshot` or `find` **clears and rebuilds** the ref store, increments `_ref_generation`, and records `initial_bounds`, `runtime_id`, and `created_at`.
2. **TTL vs LLM Latency**:
   - Default TTL is **2500 ms** (customizable via `VOILA_REF_TTL_MS`).
   - **Generation Bypass**: If the caller provides a matching `ref_generation` (`ref_generation == _ref_generation`), the TTL expiration check is bypassed entirely because generation match guarantees the ref belongs to the current snapshot.
   - If `ref_generation` does not match, resolution fails with `error: ref_generation_mismatch`.
   - If `ref_generation` is omitted (0) and ref age exceeds TTL, resolution fails with `error: ref_expired`.
   - In strict mode (`VOILA_REQUIRE_REF_GENERATION=1`), omitting `ref_generation` returns `error: ref_generation_required`.
   - If the ref store is empty, attempting an act returns `error: snapshot_required`.
3. **Resilient Re-bind**:
   - If COM pointer validation fails (`ref_stale`) or the control shifted position (`target_moved`), the resolver executes a scoped search (up to 200 nodes under the same HWND).
   - Matching priority: `AutomationId` → `RuntimeId` array match → `Name + Role`.
   - If successfully rebound, `entry["rebound"] = True` is marked and logged in debug.

---

## cursor_motion Contract

- `go(x, y, click=None, drag_to=None, duration_ms=None)` — single entry point.  
- Minimum-jerk speed profile + cubic Bézier curve + Gaussian pixel noise.  
- Duration auto-scaled by distance: clamp `[180, 900]` ms.  
- Pre-click hover `30–120 ms`; mouse-down/up gap `30–80 ms`.  
- Returns telemetry `{x, y, moved, duration_ms, distance_px}`.  
- Set `VOILA_CURSOR_DEBUG=1` or `VOILA_AUTOMATION_DEBUG=1` for verbose telemetry retention.

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
| `button` | string | Mouse button for click actions (`left`, `right`, `double`, default `left`) |
| `ref_generation` | int | Expected snapshot generation ID returned by snapshot/find for stale ref verification |

### Actions

| Action | Description |
|---|---|
| `list_windows` | All top-level window titles + PIDs |
| `foreground` | Current foreground window info |
| `snapshot` | Full compact tree with refs, bounds, and `ref_generation` |
| `find` | Filter elements by selector; return matches and `ref_generation` |
| `move_cursor` | Humanized move only, no click |
| `invoke` | Pattern-first Invoke/Toggle/SelectionItem (zero-pixel) → fallback to left click |
| `click_ref` | Pattern-first for left click → fallback to SendInput click |
| `right_click` | Humanized right-click via SendInput |
| `set_value` | Pattern-first ValuePattern (zero-pixel) → fallback to click + SendKeys |
| `type_keys` | Send keys to focused control (optionally focus via ref first) |
| `toggle` | Pattern-first Toggle (zero-pixel) → fallback to click |
| `focus` | Set keyboard focus |
| `select` | Pattern-first SelectionItem (zero-pixel) → fallback to click |
| `drag_ref` | Humanized drag from ref to `x,y` or another ref |
| `scroll` | Wheel scroll control (`up`, `down`, or signed integer delta) |

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
  "cursor": { "x": 140, "y": 215, "moved": false, "duration_ms": 0, "distance_px": 0 },
  "error": null
}
```

### Hit Targeting & Click Stack Hierarchy

1. **Pattern Short-Circuit (Zero-Pixel)**:
   Prior to any mouse motion or click point calculation, `act_invoke` and `act_click_ref` check for Microsoft UIA patterns:
   - `InvokePattern` (`method="invoke"`)
   - `TogglePattern` (`method="toggle"`)
   - `SelectionItemPattern` (`method="select"`)
   When available, the pattern executes immediately with zero pixel displacement, bypassing motion planning entirely.
2. **Validated Clickable Point**: When physical pixel dispatch is required, `GetClickablePoint()` is validated to ensure it lies strictly inside the control's bounding box and within the virtual screen bounds.
3. **Small Control Center**: For controls with `w <= 300` and `h <= 100`, the geometric center is targeted safely.
4. **Actionable Child Search**: For large panes/groups (`w > 300` or `h > 100`), the walker inspects children for actionable roles (`ButtonControl`, `HyperlinkControl`, etc.) and pattern-capable controls to avoid clicking dead center background areas.
5. **Center Fallback with Warning**: If no actionable child is identified, center is clicked and `target_warning: "large_pane_center_click_warning"` is returned.

### Win32 Input & Synchronization

- **SendInput API & Move+Down Batching**: Physical clicks batch `MOUSEEVENTF_MOVE` and `MOUSEEVENTF_DOWN` into a single `SendInput` call with absolute virtual desktop normalization (`0..65535` across multi-monitors via `SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN`). Falls back to `mouse_event` only if SendInput returns 0.
- **Per-Monitor V2 DPI Awareness**: Process initialized with `SetProcessDpiAwarenessContext(c_void_p(-4))` (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2) with fallback to `shcore.SetProcessDpiAwareness(2)`. This prevents coordinate scaling mismatch across multi-DPI displays.
- **Atomic Mutexes**: Cross-process Win32 named mutexes (`VoilaGlobalUIAMutex`, `VoilaGlobalMouseMutex`) guarantee that mouse teleportation, click down/up, and cursor restoration execute in an atomic critical section without race conditions.
- **Calculative `target_moved` & Re-bind**: Elements track initial bounds `bw, bh`. Element is flagged moved only if:
  `dx > max(50, 0.35 * bw) or dy > max(50, 0.35 * bh) or dc > max(40, 0.25 * max(bw, bh))`.
  On target moved, the resolver performs a silent re-bind attempt before returning `target_moved`.
- **Postcondition Verification**: `toggle` and `set_value` actions inspect resulting UI state and perform one automatic retry with `VOILA_CURSOR_PRECISION=1` if the state did not change.

### Error Codes

| Code | Meaning |
|---|---|
| `platform` | Not running on Windows |
| `not_found` | Window or element not found |
| `snapshot_required` | Ref store empty; caller must invoke `snapshot` or `find` first |
| `ref_generation_required` | Strict mode active (`VOILA_REQUIRE_REF_GENERATION=1`) and no `ref_generation` supplied |
| `ref_stale` | Element ref COM pointer is invalid and could not be rebound |
| `ref_expired` | Ref is older than `VOILA_REF_TTL_MS` (default 2500ms) without generation bypass |
| `ref_generation_mismatch` | Ref generation does not match the current snapshot generation |
| `ref_offscreen` | Control has `IsOffscreen=True` |
| `target_moved` | Element shifted position beyond scaled tolerance thresholds |
| `target_disabled` | Control is disabled and cannot be acted upon |
| `target_offscreen` | Control is clipped or completely off-screen |
| `tree_unavailable` | UIA tree cannot be read |
| `unsupported` | Action not available for this control type |
| `invalid_args` | Missing or malformed arguments |
