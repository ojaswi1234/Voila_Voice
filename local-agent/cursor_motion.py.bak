"""cursor_motion.py — Unified AI cursor module for Voila desktop_automation.

Single implementation for ALL pointer motion. No other module may move the
mouse for desktop_automation purposes.

Public API:
    get_pos()  -> (x, y)
    set_goal(x, y, *, click=None, drag_to=None, duration_ms=None)
    move_to_goal() -> telemetry dict
    go(x, y, *, click=None, drag_to=None, duration_ms=None) -> telemetry dict

Set VOILA_CURSOR_DEBUG=1 to enable verbose timing logs to stderr.
"""
import os, sys, math, time, random, ctypes

# ─── Debug logging ────────────────────────────────────────────────────────────
_DEBUG = os.environ.get("VOILA_CURSOR_DEBUG", "0") == "1"

def _log(msg: str):
    if _DEBUG:
        print(f"[cursor_motion] {msg}", file=sys.stderr, flush=True)

# ─── Win32 raw mouse input ─────────────────────────────────────────────────────
_user32 = ctypes.windll.user32

def _set_cursor_pos(x: int, y: int):
    """Move the real system cursor (Win32 SetCursorPos). Visible to user."""
    _user32.SetCursorPos(int(x), int(y))

def _get_cursor_pos() -> tuple[int, int]:
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def _mouse_event(flags: int, dx: int = 0, dy: int = 0, data: int = 0):
    _user32.mouse_event(flags, dx, dy, data, 0)

MOUSEEVENTF_LEFTDOWN   = 0x0002
MOUSEEVENTF_LEFTUP     = 0x0004
MOUSEEVENTF_RIGHTDOWN  = 0x0008
MOUSEEVENTF_RIGHTUP    = 0x0010

# ─── State ─────────────────────────────────────────────────────────────────────
_goal_x: int = 0
_goal_y: int = 0
_goal_click: str | None = None          # None | "left" | "right" | "double"
_goal_drag_to: tuple[int,int] | None = None
_goal_duration_ms: int | None = None

# ─── Humanized path math ───────────────────────────────────────────────────────

def _ease_inout(t: float) -> float:
    """Smooth-step (S-curve): ease-in/ease-out, value in [0,1]."""
    return t * t * (3.0 - 2.0 * t)

def _min_jerk(t: float) -> float:
    """Minimum-jerk trajectory (robotic-motion literature)."""
    return 10*(t**3) - 15*(t**4) + 6*(t**5)

def _bezier_point(t: float, p0, p1, p2, p3) -> tuple[float, float]:
    """Cubic Bézier at parameter t."""
    u = 1 - t
    x = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
    y = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
    return x, y

def _compute_steps(dist: float, duration_ms: float) -> int:
    """Number of interpolation steps based on distance and time budget."""
    # aim for ~120Hz polling; at least 12 steps for short moves
    steps = max(12, int(duration_ms / 8.33))
    return min(steps, 500)   # cap to avoid CPU spike

def _pick_duration(dist: float, requested_ms: int | None) -> int:
    if requested_ms is not None:
        return max(180, min(900, requested_ms))
    # distance-scaled: ~0.5 px/ms base, clamped 180–900 ms
    raw = dist / 0.5
    return int(max(180, min(900, raw)))

def _build_path(
    x0: float, y0: float,
    x1: float, y1: float,
    steps: int,
) -> list[tuple[int, int]]:
    """Build a humanized curved path with overshoot and pixel noise."""
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)

    # Random control points that add a slight arc/curve
    perp_x, perp_y = -dy, dx   # perpendicular vector
    if dist > 0:
        perp_x, perp_y = perp_x / dist, perp_y / dist

    curve_mag = dist * random.uniform(0.06, 0.18) * random.choice([-1, 1])
    # Slight overshoot at arrival (0–8px past target, then settle)
    overshoot = random.uniform(0, min(8, dist * 0.04))

    # Bézier control points
    cp1 = (
        x0 + dx * 0.25 + perp_x * curve_mag,
        y0 + dy * 0.25 + perp_y * curve_mag,
    )
    cp2 = (
        x0 + dx * 0.75 + perp_x * curve_mag * 0.5,
        y0 + dy * 0.75 + perp_y * curve_mag * 0.5,
    )
    # overshoot point slightly past target
    over_x = x1 + (dx / dist * overshoot if dist > 0 else 0)
    over_y = y1 + (dy / dist * overshoot if dist > 0 else 0)

    path: list[tuple[int, int]] = []
    for i in range(steps + 1):
        t_raw = i / steps
        # Use min-jerk for smooth deceleration near target
        if t_raw < 0.85:
            t = _min_jerk(t_raw / 0.85) * 0.85
        else:
            # settle back from overshoot
            t = 0.85 + _ease_inout((t_raw - 0.85) / 0.15) * 0.15

        bx, by = _bezier_point(t, (x0, y0), cp1, cp2, (over_x, over_y))
        # Sub-pixel noise (±1 px)
        nx = bx + random.gauss(0, 0.4)
        ny = by + random.gauss(0, 0.4)
        path.append((int(round(nx)), int(round(ny))))

    # Ensure exact target at the end (settle the overshoot)
    path.append((int(round(x1)), int(round(y1))))
    return path

# ─── Click helpers ─────────────────────────────────────────────────────────────

def _do_click(kind: str):
    """Perform a click at current cursor position with realistic timing."""
    hover_ms = random.uniform(30, 120)
    time.sleep(hover_ms / 1000)

    down_ms = random.uniform(30, 80)

    if kind == "left":
        _mouse_event(MOUSEEVENTF_LEFTDOWN)
        time.sleep(down_ms / 1000)
        _mouse_event(MOUSEEVENTF_LEFTUP)
    elif kind == "right":
        _mouse_event(MOUSEEVENTF_RIGHTDOWN)
        time.sleep(down_ms / 1000)
        _mouse_event(MOUSEEVENTF_RIGHTUP)
    elif kind == "double":
        _mouse_event(MOUSEEVENTF_LEFTDOWN)
        time.sleep(down_ms / 1000)
        _mouse_event(MOUSEEVENTF_LEFTUP)
        time.sleep(random.uniform(40, 80) / 1000)
        _mouse_event(MOUSEEVENTF_LEFTDOWN)
        time.sleep(down_ms / 1000)
        _mouse_event(MOUSEEVENTF_LEFTUP)

# ─── Public API ────────────────────────────────────────────────────────────────

def get_pos() -> tuple[int, int]:
    """Return current real system cursor position."""
    return _get_cursor_pos()

def set_goal(
    x: int, y: int,
    *,
    click: str | None = None,
    drag_to: tuple[int, int] | None = None,
    duration_ms: int | None = None,
):
    """
    Set movement goal. Does NOT move yet — call move_to_goal() to execute.
    click: None | "left" | "right" | "double"
    drag_to: (x2, y2) endpoint for humanized drag
    """
    global _goal_x, _goal_y, _goal_click, _goal_drag_to, _goal_duration_ms
    _goal_x = int(x)
    _goal_y = int(y)
    _goal_click = click
    _goal_drag_to = drag_to
    _goal_duration_ms = duration_ms

def move_to_goal() -> dict:
    """
    Execute humanized movement to the current goal.
    Returns telemetry dict: {x, y, moved, duration_ms, distance_px}
    """
    sx, sy = _get_cursor_pos()
    gx, gy = _goal_x, _goal_y
    dist = math.hypot(gx - sx, gy - sy)

    duration_ms = _pick_duration(dist, _goal_duration_ms)
    steps = _compute_steps(dist, duration_ms)

    _log(f"move ({sx},{sy}) → ({gx},{gy})  dist={dist:.0f}px  dur={duration_ms}ms  steps={steps}")

    t_start = time.perf_counter()

    if dist < 2:
        # Already there — still do a small settle jitter so it's not instant
        _set_cursor_pos(gx, gy)
        time.sleep(random.uniform(30, 80) / 1000)
    else:
        path = _build_path(sx, sy, gx, gy, steps)
        step_delay = duration_ms / 1000 / max(len(path), 1)

        for px, py in path:
            _set_cursor_pos(px, py)
            time.sleep(step_delay)

    # Final exact position
    _set_cursor_pos(gx, gy)

    # Drag: press down, move to target, release
    if _goal_drag_to is not None:
        dx2, dy2 = _goal_drag_to
        d_dist = math.hypot(dx2 - gx, dy2 - gy)
        d_dur = _pick_duration(d_dist, None)
        d_steps = _compute_steps(d_dist, d_dur)
        d_path = _build_path(gx, gy, dx2, dy2, d_steps)
        _mouse_event(MOUSEEVENTF_LEFTDOWN)
        d_delay = d_dur / 1000 / max(len(d_path), 1)
        for px, py in d_path:
            _set_cursor_pos(px, py)
            time.sleep(d_delay)
        _set_cursor_pos(dx2, dy2)
        _mouse_event(MOUSEEVENTF_LEFTUP)

    # Click (if requested) — only when NOT dragging
    elif _goal_click is not None:
        _do_click(_goal_click)

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    cx, cy = _get_cursor_pos()

    return {
        "x": cx,
        "y": cy,
        "moved": dist >= 2,
        "duration_ms": elapsed_ms,
        "distance_px": int(dist),
    }

def go(
    x: int, y: int,
    *,
    click: str | None = None,
    drag_to: tuple[int, int] | None = None,
    duration_ms: int | None = None,
) -> dict:
    """
    One-shot: set_goal + move_to_goal combined.
    The canonical entry point for all callers.
    """
    set_goal(x, y, click=click, drag_to=drag_to, duration_ms=duration_ms)
    return move_to_goal()

# ─── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    os.environ["VOILA_CURSOR_DEBUG"] = "1"
    cx, cy = get_pos()
    print(f"Current pos: {cx}, {cy}", file=sys.stderr)
    # Move 200px right, 100px down
    tel = go(cx + 200, cy + 100, click="left")
    print(json.dumps({"test": "cursor_motion", "telemetry": tel}))
