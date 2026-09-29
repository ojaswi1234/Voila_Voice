# Voila Security Guardrails & Policy Engine

## Overview

Voila employs a strict "Deny by Default, Allow by User Popup" security model to prevent catastrophic actions (e.g. wiping disks, destroying boot configurations) while maintaining agent autonomy.

The security model consists of a centralized policy engine (`security_policy.go`) that evaluates actions *before* they are sent to the OS or the Python Desktop Automation Bridge.

## Policy Engine (`security_policy.go`)

All rules are centrally managed in `security_rules.json`. The Go policy engine intercepts actions from the AI and categorizes them into three levels:
1. **Allow**: Safe actions (like viewing a window, taking a screenshot, listing directories) proceed instantly without user friction.
2. **Deny**: Catastrophic, unrecoverable actions (like `format c:`) are hard-blocked outright. The model is given a clear error explaining why.
3. **Approve**: Actions that are highly destructive but *potentially* intended by the user (like formatting a non-system volume, typing certain commands) are paused.

### The Security Permission Popup
When an action is evaluated as `Approve`, the tool execution pauses, and a push notification / websocket message is sent to the user's mobile app.

The mobile app displays a rich **Security Permission Popup** containing:
- **Risk Level**: (Medium / High / Critical)
- **Action**: (Terminal, Desktop Click, Desktop Typing)
- **Target**: (Window title, Control name, or Command snippet)
- **Why blocked**: (A plain English explanation from the rules JSON)

The user has two choices:
- **DENY** (Default): Blocks the action. The AI receives a `permission_denied` error with an injected prompt note instructing it *not* to blindly loop/retry the same action, but instead ask the user for a safer alternative.
- **ALLOW ONCE**: If the user genuinely requested this destructive task, they can tap "Allow Once". The action immediately resumes and executes once.

### Defense in Depth (Python)
As an added layer of safety, the `desktop_core.py` automation bridge implements a redundant Python-side check for protected windows (e.g., UAC, Registry Editor) and destructive patterns. If an action somehow bypasses the Go engine, the Python engine will return `{"ok":false, "error":"policy_blocked"}` without clicking or typing.

### Audit Logging
Every policy evaluation (whether blocked automatically, allowed by the user, or denied by the user) is recorded in `security_audit.jsonl`.
This log omits sensitive command payloads and instead only records the action metadata, matched rule, and decision.

## Modifying Rules
To modify security constraints, edit `local-agent/security_rules.json`.
Do not duplicate dangerous strings inside `main.go`.
