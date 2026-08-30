"""
Test automation script for dashboard popup movement.
This script tests the window movement and centering logic.
"""
import tkinter as tk
import time

def test_popup_movement():
    """Test popup window movement and centering"""
    root = tk.Tk()
    root.title("Test Popup Movement")
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    root.attributes('-transparentcolor', 'magenta')
    root.config(bg='magenta')

    # Initial position (bottom right like original)
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = screen_width - 320
    y = screen_height - 120
    root.geometry(f"300x90+{x}+{y}")

    canvas = tk.Canvas(root, width=300, height=90, bg='magenta', highlightthickness=0)
    canvas.pack()

    # Draw test popup
    pill = canvas.create_rectangle(10, 10, 290, 80, fill='#1e1e24', outline='#3a3a40', width=2)
    test_text = canvas.create_text(150, 45, text="TEST POPUP", fill="#888888", font=("Segoe UI", 12, "bold"))

    print(f"[TEST] Initial position: {x}, {y}")
    print(f"[TEST] Screen size: {screen_width}x{screen_height}")

    # Wait 2 seconds
    root.update()
    time.sleep(2)

    # Calculate center
    target_w, target_h = 920, 620
    center_x = (screen_width - target_w) // 2
    center_y = (screen_height - target_h) // 2
    print(f"[TEST] Target center: {center_x}, {center_y}")
    print(f"[TEST] Target size: {target_w}x{target_h}")

    # Animate to center
    steps = 25
    for i in range(steps + 1):
        progress = i / steps
        ease = 1 - pow(1 - progress, 3)  # Ease-out cubic

        current_x = int(x + (center_x - x) * ease)
        current_y = int(y + (center_y - y) * ease)
        new_width = int(300 + (920 - 300) * ease)
        new_height = int(90 + (620 - 90) * ease)

        root.geometry(f"{new_width}x{new_height}+{current_x}+{current_y}")
        canvas.config(width=new_width, height=new_height)

        # Reposition elements
        canvas.coords(pill, 10, 10, new_width-10, new_height-10)
        canvas.coords(test_text, new_width//2, new_height//2)

        root.update()
        time.sleep(0.016)  # ~60fps

    print(f"[TEST] Final position: {root.winfo_x()}, {root.winfo_y()}")
    print(f"[TEST] Final size: {root.winfo_width()}x{root.winfo_height()}")

    # Wait 3 seconds at center
    time.sleep(3)

    # Animate back
    for i in range(steps + 1):
        progress = i / steps
        ease = 1 - pow(1 - progress, 3)

        current_x = int(center_x + (x - center_x) * ease)
        current_y = int(center_y + (y - center_y) * ease)
        new_width = int(920 + (300 - 920) * ease)
        new_height = int(620 + (90 - 620) * ease)

        root.geometry(f"{new_width}x{new_height}+{current_x}+{current_y}")
        canvas.config(width=new_width, height=new_height)

        canvas.coords(pill, 10, 10, new_width-10, new_height-10)
        canvas.coords(test_text, new_width//2, new_height//2)

        root.update()
        time.sleep(0.016)

    print(f"[TEST] Back to original: {root.winfo_x()}, {root.winfo_y()}")
    print(f"[TEST] Back to size: {root.winfo_width()}x{root.winfo_height()}")

    # Wait 2 seconds
    time.sleep(2)

    root.destroy()
    print("[TEST] Complete")

if __name__ == "__main__":
    test_popup_movement()
