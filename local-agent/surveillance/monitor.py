import ctypes
import time
import requests
import json
import os
import sys

# Windows API structs
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32 = ctypes.windll.user32

def get_mouse_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def send_alert(reason):
    try:
        requests.post('http://localhost:8088/surveillance/alert', json={'reason': reason})
    except:
        pass

def main():
    last_x, last_y = get_mouse_pos()
    last_alert_time = 0
    debounce_seconds = 5

    # Known key states to prevent firing continuously while held down
    key_states = [0] * 256

    while True:
        current_time = time.time()
        triggered = False
        reason = ""

        # 1. Check mouse movement
        mx, my = get_mouse_pos()
        if abs(mx - last_x) > 50 or abs(my - last_y) > 50:
            triggered = True
            reason = "mouse movement"
            last_x, last_y = mx, my

        # 2. Check keyboard activity
        # We check a few important keys or all keys. Looping 0-255 is fast enough.
        for i in range(1, 256):
            state = user32.GetAsyncKeyState(i)
            # MSB is set if key is currently down
            is_down = (state & 0x8000) != 0
            if is_down and not key_states[i]:
                # Key just pressed
                if i == 0xAD: # VK_VOLUME_MUTE
                    triggered = True
                    reason = "mute key pressed"
                else:
                    # Ignore mouse clicks (0x01, 0x02) to avoid double trigger with movement, 
                    # but if they click we can trigger too.
                    if i not in (1, 2, 4, 5, 6): 
                        triggered = True
                        reason = "keyboard activity"
            key_states[i] = is_down

        if triggered and (current_time - last_alert_time > debounce_seconds):
            send_alert(reason)
            last_alert_time = current_time

        time.sleep(0.05) # 20 Hz

if __name__ == "__main__":
    main()
