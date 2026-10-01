# Voila Security Guardrails & Policy Engine

## Overview

Voila employs a strict "Deny by Default, Allow by User Popup" security model to prevent catastrophic actions (e.g. wiping disks, destroying boot configurations) while maintaining agent autonomy.

The security model consists of a centralized policy engine (security_policy.go) that evaluates actions *before* they are sent to the OS or the Python Desktop Automation Bridge.

## Single Source of Truth (SSOT)

All rules are centrally managed in security_rules.json (with an embedded fallback in security_policy.go).
The Go policy engine intercepts actions from the AI and categorizes them into three levels:
1. **Allow**: Safe actions (like viewing a window, taking a screenshot, listing directories) proceed instantly without user friction.
2. **Deny**: Catastrophic, unrecoverable actions (like ormat c:) are hard-blocked outright. The model is given a clear error explaining why.
3. **Approve**: Actions that are highly destructive but *potentially* intended by the user (like formatting a non-system volume, typing certain commands) are paused.

The engine completely avoids hard-coding rules in main.go. EvaluateTerminalCommand and EvaluateDesktopAction provide a clean boundary.

### The Security Permission Popup
When an action is evaluated as Approve, the tool execution pauses, and a push notification / websocket message is sent to the user's mobile app.

The mobile app displays a rich **Security Permission Popup** containing:
- **Risk Level**: (Medium / High / Critical)
- **Action**: (Terminal, Desktop Click, Desktop Typing)
- **Target**: (Window title, Control name, or Command snippet)
- **Why blocked**: (A plain English explanation from the rules JSON)

The user has two choices:
- **DENY** (Default): Blocks the action. The AI receives a permission_denied error with an injected prompt note instructing it *not* to blindly loop/retry the same action, but instead ask the user for a safer alternative.
- **ALLOW ONCE**: If the user genuinely requested this destructive task, they can tap "Allow Once". The action immediately resumes and executes once.

### Aegis ML Module (Optional Firewall)
egis_core.py provides an ML-based evaluation layer. Currently, Aegis fails OPEN if it crashes or fails to import, ensuring the agent remains functional without bricking on environment failures.

### Defense in Depth (Python)
As an added layer of safety, the desktop_core.py automation bridge implements a redundant Python-side check for destructive keywords and protected windows. If an action bypasses the Go engine, the Python engine will return policy_blocked before clicking or typing.

### Audit Logging
Every policy evaluation (blocked automatically, allowed by user, or denied by user) is recorded in security_audit.jsonl.

## Modifying Rules
To modify security constraints, edit local-agent/security_rules.json.

## Residual Risks & Known Limitations
- **Substring Bypass**: Terminal rules rely heavily on substring matching. Base64 encoding, obfuscation, or subtle flags can bypass these checks.
- **LLM Snapshot Order**: The LLM may sometimes guess refs before taking a snapshot. The engine correctly blocks stale refs, but it adds latency.
- **Bare "Delete" Keywords**: To prevent false positives, we check for multi-word phrases (like "empty recycle", "delete permanently", "format volume") instead of bare "delete". Bare "delete" is a known residual risk that is omitted from the UI destructive filter to avoid false positives on benign apps.
