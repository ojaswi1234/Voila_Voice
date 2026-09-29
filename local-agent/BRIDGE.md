# Browser ↔ Desktop Bridge

## Overview
The `browser_desktop_bridge` tool provides an **optional collaboration layer** between `browser_automation` and `desktop_automation`.
It allows the agent to calculate DOM coordinates via Chrome DevTools Protocol (CDP) and execute physically humanized clicks via OS-level Windows APIs (UIA).

## Purpose
- Bypass stubborn browser anti-bot overlays.
- Click elements when standard Playwright `element.click()` is suppressed or intercepted.
- Fallback for non-DOM popups.

## Architecture
1. **`browser_guide.py`**: A minimal script that attaches to the *existing* CDP debugging port (`9222`) used by the browser, queries the DOM for `getBoundingClientRect`, and calculates the exact OS screen coordinates by offsetting `window.screenX/Y` borders.
2. **`bridge_constructor.py`**: Python orchestrator that runs `browser_guide.py` to get exact coordinates, validates confidence thresholds, and leverages `cursor_motion.py` to execute a humanized click on the desktop. It then re-verifies the DOM state.
3. **`main.go`**: Provides the `browser_desktop_bridge` tool. It enforces Opt-in, Security policies (popup), and Circuit Breaking.

## Strict Opt-in
The bridge is **OFF** by default.
It cannot be invoked indiscriminately upon every browser failure. 
To use the bridge, you must enable the session using:
```json
{
  "action": "enable_session"
}
```
Only do this when the user's intent clearly dictates bridging tools together (e.g. "click that popup with a real mouse", "collaborate desktop and browser").

## Bridge Circuit Breaker
Unlike the auth global circuit breaker which kills all automation, the **Bridge Circuit Breaker** is isolated.
- **Trip Condition**: 5 consecutive failures (e.g. low confidence, unreachable elements, CDP disconnect) within 10 minutes.
- **Consequence**: The bridge becomes locked (`bridge_circuit_open`). Standard `browser_automation` and `desktop_automation` continue to work natively.
- **Recovery**: Cools down automatically after 10 minutes.

## Security Integration
All guided clicks are treated as OS-level actions. The coordinates might map onto sensitive native applications if the browser window isn't foregrounded. Therefore, `main.go` passes the bridge target through `EvaluateDesktopAction()` and the user's **Security Permission Popup**.

## Tests & Reliability
This bridge handles screen coordinates gracefully via logical-to-physical bounds, compensating for Windows scaling (DPR).
LLMs are blocked from guessing random screen coordinates; all paths go directly through programmatic geometric derivation.
