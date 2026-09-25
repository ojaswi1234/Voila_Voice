import subprocess
import time

def run_cmd(action, val=""):
    print(f"Executing: {action} {val}")
    cmd = ["python", "local-agent/desktop_tools.py", "--action", action]
    if val: cmd.extend(["--value", val])
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(f"Result: {res.stdout.strip()}")
    time.sleep(1)

print("Starting automation task...")
run_cmd("switch_window", "next")
run_cmd("switch_window", "next")
run_cmd("switch_desktop", "task_view")
time.sleep(1)
run_cmd("switch_desktop", "task_view")
print("Task completed!")
