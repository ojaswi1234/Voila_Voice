import re
with open('local-agent/cursor_motion.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace the end of _do_click
old_pulse = '''    # Pulse the overlay to show click
    try: _overlay_sock.sendto(b"HIDE", ("127.0.0.1", _OVERLAY_PORT))
    except: pass
    time.sleep(0.05)
    _set_cursor_pos(cx, cy)'''

new_pulse = '''    # Pulse the overlay to show click
    try: _overlay_sock.sendto(b"HIDE", ("127.0.0.1", _OVERLAY_PORT))
    except: pass
    time.sleep(0.15)
    # Briefly show the click location
    _set_cursor_pos(cx, cy)
    time.sleep(0.2)
    # Hide the cursor so it doesn't stay permanently stuck on screen
    try: _overlay_sock.sendto(b"HIDE", ("127.0.0.1", _OVERLAY_PORT))
    except: pass'''

if old_pulse in text:
    text = text.replace(old_pulse, new_pulse)
else:
    print("Could not find old_pulse")

with open('local-agent/cursor_motion.py', 'w', encoding='utf-8') as f:
    f.write(text)
