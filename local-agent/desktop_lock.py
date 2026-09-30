import ctypes
import os

_IS_GRAPHIFY_AGENT = os.environ.get("VOILA_AGENT_PORT") is not None
_uia_mutex = None
_mouse_mutex = None

if _IS_GRAPHIFY_AGENT:
    try:
        _uia_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "VoilaGlobalUIAMutex")
        _mouse_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "VoilaGlobalMouseMutex")
    except Exception:
        pass

def acquire_uia():
    if _uia_mutex:
        ctypes.windll.kernel32.WaitForSingleObject(_uia_mutex, 0xFFFFFFFF)

def release_uia():
    if _uia_mutex:
        ctypes.windll.kernel32.ReleaseMutex(_uia_mutex)

def acquire_mouse():
    if _mouse_mutex:
        ctypes.windll.kernel32.WaitForSingleObject(_mouse_mutex, 0xFFFFFFFF)

def release_mouse():
    if _mouse_mutex:
        ctypes.windll.kernel32.ReleaseMutex(_mouse_mutex)

class UIA_Lock:
    def __enter__(self):
        acquire_uia()
    def __exit__(self, exc_type, exc_val, exc_tb):
        release_uia()

class UIALock_Suspend:
    """Temporarily releases the UIA lock so other agents can work during long visual animations."""
    def __enter__(self):
        release_uia()
    def __exit__(self, exc_type, exc_val, exc_tb):
        acquire_uia()
