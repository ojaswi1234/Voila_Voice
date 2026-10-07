# Voila Surveillance Mode (Prototype)

## Overview
Surveillance mode monitors the desktop for unauthorized physical or remote activity (keyboard, mouse movement, mute button press) and gates sensitive agent tools when locked.

## UI Integrations
- **Mobile App**: Accessible via the main navigation drawer -> **Surveillance**. From there, you can Arm/Disarm and Lock/Unlock.
- **Local TUI (Windows Terminal)**: The background terminal will dynamically change its window title and display a printed banner when the surveillance state changes (ARMED vs LOCKED vs DISARMED).

## Gesture Controls
Gestures are captured using the local agent's gesture module. You can train and test gestures.

### 1. Training the Gestures
To use gestures, you must first train the agent with your baseline Omega gesture.
- The Omega gesture is the Greek letter `Ω`.
- It can be drawn with your mouse or touchpad.
- To train, send an API request (or ask the AI to run):
  `Invoke-RestMethod -Uri http://localhost:8088/surveillance/gesture/train -Method POST`
- After firing that request, you have ~2 seconds to quickly draw the `Ω` path.

### 2. Locking
- Once armed (or anytime you want to lock), start a lock capture:
  `Invoke-RestMethod -Uri "http://localhost:8088/surveillance/gesture/capture?intent=lock" -Method POST`
- Draw the `Ω` path.
- The agent will recognize the path, and transition the surveillance state to `LOCKED`.
- While `LOCKED`, the agent will strictly refuse `run_terminal`, `desktop_automation`, and `browser_automation` tool calls.

### 3. Unlocking (Water Image)
- To unlock a locked session locally, you must draw a top-bottom inverted (Water Image) Omega `Ω`. 
- Imagine the `Ω` reflected upside down.
- Send the unlock capture request:
  `Invoke-RestMethod -Uri "http://localhost:8088/surveillance/gesture/capture?intent=unlock" -Method POST`
- Draw the inverted `Ω` path.
- The agent calculates the DTW distance against the inverted template and unlocks the agent if matched.

## Notes
- **Prototype Quality**: Hardware tracking uses low-level `ctypes.windll.user32` polling rather than deep kernel hooks.
- **Mute Key Monitoring**: Detects the `VK_VOLUME_MUTE` key edge.
- **Mouse Movement**: Movement must exceed a basic threshold (e.g., >50 pixels) to trigger an alert.
