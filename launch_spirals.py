import sys
import os
import subprocess

here = os.path.dirname(os.path.abspath(__file__))
script = os.path.join(here, "draw_spirals.py")
python_exe = sys.executable.replace("python.exe", "pythonw.exe")
cmd = f'{python_exe} "{script}"'

try:
    import win32com.client
    import pythoncom
    pythoncom.CoInitialize()
    wmi = win32com.client.Dispatch("WbemScripting.SWbemLocator").ConnectServer(".", "root\\cimv2")
    process_startup = wmi.Get("Win32_ProcessStartup").SpawnInstance_()
    process_startup.ShowWindow = 0
    result, pid = wmi.Get("Win32_Process").Create(cmd, None, process_startup)
    print(f"Launched in Session 1 via WMI. Result={result}, PID={pid}")
except Exception as e:
    print(f"WMI failed: {e}. Fallback to subprocess.")
    subprocess.Popen([python_exe, script], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
