"""desktop_lock.py — Process-wide and Cross-process Synchronization for Voila Automation.

Guarantees thread-safety and multi-agent anti-choking for both:
1. Windows UI Automation (COM) calls (VoilaGlobalUIAMutex)
2. Physical/SendInput mouse input critical sections (VoilaGlobalMouseMutex)
"""
import ctypes
import os
import sys
import threading

_is_windows = sys.platform == "win32"
_thread_uia_lock = threading.RLock()
_thread_mouse_lock = threading.RLock()

_uia_mutex = None
_mouse_mutex = None

if _is_windows:
    try:
        # Create or open global cross-process named mutexes
        # Available across all Voila agent, bridge, and tool processes
        kernel32 = ctypes.windll.kernel32
        _uia_mutex = kernel32.CreateMutexW(None, False, "VoilaGlobalUIAMutex")
        _mouse_mutex = kernel32.CreateMutexW(None, False, "VoilaGlobalMouseMutex")
    except Exception:
        _uia_mutex = None
        _mouse_mutex = None

def acquire_uia(timeout_ms: int = 0xFFFFFFFF):
    """Acquire the UIA COM mutex (in-process RLock + global Win32 mutex)."""
    _thread_uia_lock.acquire()
    if _uia_mutex and _is_windows:
        try:
            ctypes.windll.kernel32.WaitForSingleObject(_uia_mutex, int(timeout_ms))
        except Exception:
            pass

def release_uia():
    """Release the UIA COM mutex."""
    if _uia_mutex and _is_windows:
        try:
            ctypes.windll.kernel32.ReleaseMutex(_uia_mutex)
        except Exception:
            pass
    try:
        _thread_uia_lock.release()
    except RuntimeError:
        pass

def acquire_mouse(timeout_ms: int = 0xFFFFFFFF):
    """Acquire the mouse input mutex for SendInput / cursor critical section."""
    _thread_mouse_lock.acquire()
    if _mouse_mutex and _is_windows:
        try:
            ctypes.windll.kernel32.WaitForSingleObject(_mouse_mutex, int(timeout_ms))
        except Exception:
            pass

def release_mouse():
    """Release the mouse input mutex."""
    if _mouse_mutex and _is_windows:
        try:
            ctypes.windll.kernel32.ReleaseMutex(_mouse_mutex)
        except Exception:
            pass
    try:
        _thread_mouse_lock.release()
    except RuntimeError:
        pass

class UIA_Lock:
    """Context manager for UIA tree walks and pattern calls."""
    def __enter__(self):
        acquire_uia()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        release_uia()

class UIALock_Suspend:
    """Temporarily releases the UIA lock so other agents/threads can work during long visual animations."""
    def __enter__(self):
        release_uia()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        acquire_uia()

class Mouse_Lock:
    """Context manager ensuring atomic physical mouse movement, click down/up, and restoration."""
    def __enter__(self):
        acquire_mouse()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        release_mouse()
