import ctypes
import time
import requests
import json
import os
import sys
import logging

log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voila_debug.log")
logging.basicConfig(filename=log_file, level=logging.DEBUG, format='%(asctime)s [MONITOR] %(message)s')

# Windows API structs
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

user32 = ctypes.windll.user32

def get_mouse_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def send_alert(reason):
    logging.info(f"Triggering alert for: {reason}")
    try:
        r = requests.post('http://localhost:8088/surveillance/alert', json={'reason': reason}, timeout=2)
        logging.info(f"Alert sent successfully, response: {r.status_code}")
    except Exception as e:
        logging.error(f"Failed to send alert: {e}")

def main():
    logging.info("Surveillance monitor script started.")
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
                    if i not in (1, 2, 4, 5, 6): 
                        triggered = True
                        reason = "keyboard activity"
            key_states[i] = is_down

        if triggered and (current_time - last_alert_time > debounce_seconds):
            # Delay slightly to allow user to finish the unlock gesture
            time.sleep(1.5)
            try:
                status_req = requests.get('http://localhost:8088/surveillance/status', timeout=1)
                if status_req.json().get('locked', False):
                    send_alert(reason)
                    last_alert_time = time.time()
            except Exception as e:
                # If backend is unreachable, default to firing the alert
                send_alert(reason)
                last_alert_time = time.time()

        time.sleep(0.05) # 20 Hz

if __name__ == "__main__":
    main()
