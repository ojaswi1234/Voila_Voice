import json
import time
import subprocess
import os
import ctypes

def call_tool(action, value=None, window=None):
    print(f"[*] Calling: {action} (value={value}, window={window})")
    cmd = ["python", "local-agent/desktop_tools.py", "--action", action]
    if value:
        cmd.extend(["--value", value])
    if window:
        cmd.extend(["--window", window])
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(res.stdout.strip())
        print(f"    -> OK: {data.get('ok')} | {data.get('message', '')}")
        return data
    except Exception as e:
        print(f"    -> Error parsing JSON: {res.stdout.strip()[:100]}")
        return None

def test_complex_flow():
    print("=== STARTING COMPLEX UI SYNCHRONIZATION TEST ===")
    
    # 1. Open Notepad
    call_tool("open_start_menu")
    call_tool("type_keys", "notepad")
    call_tool("type_keys", "{ENTER}")
    
    # 2. Wait for Notepad to actually appear (The fix we just implemented!)
    print("[*] Polling for Notepad (simulating LLM focus_window guardrail)...")
    call_tool("focus_window", window="Notepad")
    
    # 3. Type text safely
    call_tool("type_keys", "Hello from Desktop 1. Switching soon...")
    time.sleep(1)
    
    # 4. Create and Switch to NEW Virtual Desktop
    print("\n=== SWITCHING DESKTOPS ===")
    call_tool("switch_desktop", value="new")
    time.sleep(1)
    
    # 5. Open Calc in Desktop 2
    call_tool("open_start_menu")
    call_tool("type_keys", "calculator")
    call_tool("type_keys", "{ENTER}")
    
    # 6. Wait for Calc
    print("[*] Polling for Calculator...")
    call_tool("focus_window", window="Calculator")
    time.sleep(1)
    
    # 7. Close Calc
    call_tool("type_keys", "%{F4}") # Alt+F4 to close calculator
    
    # 8. Switch back to Desktop 1
    print("\n=== RETURNING TO DESKTOP 1 ===")
    call_tool("switch_desktop", value="prev")
    time.sleep(1)
    
    # 9. Close Notepad without saving
    print("[*] Closing Notepad")
    call_tool("focus_window", window="Notepad")
    call_tool("type_keys", "%{F4}") # Alt+F4
    time.sleep(0.5)
    call_tool("type_keys", "{TAB}") # Switch to "Don't Save"
    call_tool("type_keys", "{ENTER}")
    
    print("\n=== COMPLEX TEST COMPLETE ===")

if __name__ == "__main__":
    test_complex_flow()
